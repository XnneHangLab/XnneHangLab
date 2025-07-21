from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import faiss
import numpy as np
import shortuuid
import yaml

from lab.agent.memory import embedding
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from numpy.typing import NDArray


class CoreMemory:
    """核心记忆系统，负责长期记忆的存储和检索。

    这个类管理角色的核心长期记忆，包括记忆的加载、添加、向量化存储以及基于语义的检索。
    它使用FAISS库进行高效的相似度搜索，并将记忆持久化到YAML文件中。
    """

    # 修改构造函数以接受一个可选的配置对象，用于测试
    def __init__(self, config_settings: XnneHangLabSettings | None = None) -> None:
        """初始化核心记忆系统。

        在初始化时，会加载应用程序配置，设置记忆文件路径，
        并尝试从文件中加载现有记忆或初始化一个新的记忆文件，
        最后构建FAISS向量索引。

        Args:
            config_settings: 可选的配置设置对象。在测试时传入模拟对象，
                             在生产环境中则由内部加载。
        """
        # 如果提供了配置设置，则直接使用；否则从文件加载
        self.config: XnneHangLabSettings = (
            config_settings if config_settings else load_settings_file("lab.toml", XnneHangLabSettings)
        )
        # 根据配置更新内部参数
        self._load_configuration()

        # 用于存储记忆相关数据的数据结构
        self.raw_memory_texts: list[str] = []  # 存储原始的记忆文本内容 (用于向量化)
        self.full_memory_contents: list[str] = []  # 存储带时间戳的完整记忆内容 (用于展示)
        self.memory_uuids: list[str] = []  # 存储每个记忆的唯一标识符

        # 确保记忆文件所在的父目录存在
        self.memory_file_path.parent.mkdir(parents=True, exist_ok=True)

        # 根据记忆文件是否存在，选择加载现有记忆或初始化新记忆文件
        if self.memory_file_path.exists():
            self._load_existing_memories()
        else:
            self._initialize_new_memory_file()

        # 核心记忆的向量表示，用于FAISS索引
        # 如果没有记忆，embedding.t2vect需要处理空列表或单条"空"数据
        initial_vectors: NDArray[np.float32]
        if not self.raw_memory_texts:
            # 当没有记忆时，添加一个占位符向量以初始化FAISS索引
            initial_vectors = embedding.t2vect(["占位记忆"]).astype(np.float32)
            print("[警告] 核心记忆为空，FAISS索引将用占位向量初始化。")
        else:
            initial_vectors = embedding.t2vect(self.raw_memory_texts).astype(np.float32)

        # 初始化FAISS索引，使用内积作为相似度度量（适用于归一化向量的余弦相似度）
        # `vectors.shape[1]` 获取向量的维度
        self.faiss_index: faiss.IndexFlatIP = faiss.IndexFlatIP(initial_vectors.shape[1])
        # 将所有记忆向量添加到FAISS索引中
        self.faiss_index.add(initial_vectors)  # type: ignore

    def _load_configuration(self) -> None:
        """从配置文件中加载并更新记忆系统的相关设置。"""
        # 从已加载的配置对象中获取角色名称和用户名称
        self.character_name: str = self.config.agent.system_prompt_name
        # 假设用户名为固定值，或者也可以从配置中加载
        self.user_name: str = "xnnehang"
        # 记忆检索的相似度阈值，低于此阈值的记忆将被过滤
        self.similarity_threshold: float = 0.5
        # 核心记忆文件的存储路径，根据角色名称动态生成
        self.memory_file_path: Path = Path(f"./chat_history/{self.character_name}/core_mem.yml")

    def _load_existing_memories(self) -> None:
        """加载已存在的核心记忆文件（YAML格式）。"""
        try:
            with self.memory_file_path.open("r", encoding="utf-8") as file:
                # 使用safe_load解析YAML文件，如果文件为空则返回空字典
                data_from_file: dict[str, dict[str, Any]] = yaml.safe_load(file) or {}

            for uuid_key, record_data in data_from_file.items():
                # 确保record_data是字典类型且包含'time'和'text'键
                if isinstance(record_data, dict) and "time" in record_data and "text" in record_data:  # type: ignore
                    # 提取原始记忆文本用于向量化
                    self.raw_memory_texts.append(record_data["text"])
                    # 组合时间戳和文本作为完整的记忆内容，用于检索结果展示
                    self.full_memory_contents.append(f"记忆获取时间：{record_data['time']}\n{record_data['text']}")
                    # 存储记忆的UUID
                    self.memory_uuids.append(uuid_key)
                else:
                    print(f"[警告] 核心记忆文件中的记录格式不正确，跳过记录: {uuid_key} - {record_data}")
            print(f"[系统] 已加载 {len(self.raw_memory_texts)} 条核心记忆。")
        except FileNotFoundError:
            print(f"[错误] 核心记忆文件未找到: {self.memory_file_path}。将初始化新文件。")
            self._initialize_new_memory_file()
        except yaml.YAMLError as e:
            print(f"[错误] 解析核心记忆文件失败: {e}。文件可能已损坏，将尝试初始化新文件。")
            # 备份损坏的文件以防数据丢失，并初始化新文件
            self.memory_file_path.rename(self.memory_file_path.with_suffix(".yml.bak"))
            self._initialize_new_memory_file()
        except Exception as e:
            print(f"[错误] 加载核心记忆时发生未知错误: {e}")
            # 对于其他未知错误，也尝试初始化新文件
            self._initialize_new_memory_file()

    def _initialize_new_memory_file(self) -> None:
        """初始化新的核心记忆文件，并写入一个初始记忆条目。"""
        # 创建带有警告信息的空文件，防止用户手动修改导致索引损坏
        with self.memory_file_path.open("w", encoding="utf-8") as file:
            file.write("# 核心记忆文件，请勿自行修改！否则会丢失索引！\n")

        # 定义初始记忆条目
        current_timestamp: str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        initial_memory_text: str = "第一次与用户相遇，开始建立核心记忆。"
        initial_memory_uuid: str = self._generate_unique_id()

        # 构造初始记忆的字典结构
        initial_record_data: dict[str, dict[str, Any]] = {
            initial_memory_uuid: {"time": current_timestamp, "text": initial_memory_text}
        }

        # 将初始记忆写入到YAML文件中
        with self.memory_file_path.open("a", encoding="utf-8") as file:
            yaml.safe_dump(initial_record_data, file, allow_unicode=True, default_flow_style=False)
        print("[系统] 已初始化新的核心记忆文件并添加初始记忆。")

        # 重新加载（或首次加载）这些记忆到内存中
        # 注意：这里直接调用_load_existing_memories会再次尝试读取文件，
        # 如果文件路径不变，且内容是刚写入的，这将是正确的行为。
        self.raw_memory_texts = []  # 清空以确保重新加载
        self.full_memory_contents = []
        self.memory_uuids = []
        self._load_existing_memories()

    def _generate_unique_id(self) -> str:
        """生成一个唯一的短UUID，确保其在当前已有的记忆UUID列表中不重复。

        Returns:
            一个不重复的10位字符串UUID。
        """
        while True:
            new_uuid_candidate: str = shortuuid.ShortUUID().random(length=10)
            if new_uuid_candidate not in self.memory_uuids:
                return new_uuid_candidate

    def find_memory(self, query_text: str, retrieval_limit: int = 5) -> list[str]:
        """
        根据查询文本检索相关的核心记忆。

        Args:
            query_text: 需要检索的查询文本。
            retrieval_limit: 返回最相似记忆的数量。

        Returns:
            一个包含所有相关记忆完整内容的列表，每条记忆都包含时间戳。
        """
        # 将查询文本转换为向量
        query_vector: NDArray[np.float32] = embedding.t2vect([query_text]).astype(np.float32)

        distances: NDArray[np.float32]
        indices: NDArray[np.int64]

        # 检查索引是否为空
        if self.faiss_index.ntotal == 0:
            print("[警告] FAISS索引为空，无法执行搜索。")
            return []

        # 使用FAISS进行相似度搜索
        # distances: 相似度得分数组
        # indices: 相似记忆在self.full_memory_contents中的索引数组
        distances, indices = self.faiss_index.search(query_vector, retrieval_limit)  # type: ignore

        relevant_memories: list[str] = []
        # 遍历查询结果，distances和indices通常是二维数组
        for distance_array, index_array in zip(distances, indices, strict=True):  # type: ignore
            for similarity_score, memory_index in zip(distance_array, index_array, strict=True):
                # 检查相似度是否达到阈值，并且索引是有效的
                if similarity_score >= self.similarity_threshold and 0 <= memory_index < len(self.full_memory_contents):
                    # 获取完整的记忆内容（包含时间戳）
                    relevant_memories.append(self.full_memory_contents[memory_index])  # type: ignore

        # 返回去重后的相关记忆列表
        return list(set(relevant_memories))

    def add_memory(self, new_memory_texts: list[str]) -> None:
        """
        添加新的核心记忆内容。

        新的记忆会被向量化并添加到FAISS索引中，同时写入记忆文件以进行持久化。

        Args:
            new_memory_texts: 需要添加的原始记忆文本列表。
        """
        if not new_memory_texts:
            print("[提示] 没有新的记忆文本需要添加。")
            return

        records_to_save_to_file: dict[str, dict[str, Any]] = {}
        processed_raw_texts: list[str] = []  # 存储本批次要向量化的原始文本
        processed_full_contents: list[str] = []  # 存储本批次要添加到full_memory_contents的完整内容

        for memory_text in new_memory_texts:
            new_entry_uuid: str = self._generate_unique_id()
            current_timestamp: str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            # 准备要写入文件的记录
            records_to_save_to_file[new_entry_uuid] = {"time": current_timestamp, "text": memory_text}

            # 准备添加到内存中的列表
            processed_raw_texts.append(memory_text)
            processed_full_contents.append(f"记忆获取时间：{current_timestamp}\n{memory_text}")
            self.memory_uuids.append(new_entry_uuid)  # 更新UUID列表

        # 批量更新内存中的列表
        self.raw_memory_texts.extend(processed_raw_texts)
        self.full_memory_contents.extend(processed_full_contents)

        # 追加写入记忆文件
        with self.memory_file_path.open("a", encoding="utf-8") as file:
            yaml.safe_dump(records_to_save_to_file, file, allow_unicode=True, default_flow_style=False)

        # 更新FAISS索引
        # 对新添加的记忆文本进行向量化
        new_vectors_for_index: NDArray[np.float32] = embedding.t2vect(new_memory_texts).astype(np.float32)
        # 将新向量添加到FAISS索引中
        self.faiss_index.add(new_vectors_for_index)  # type:ignore

        print(f"[系统提示] 已成功添加 {len(new_memory_texts)} 条核心记忆。")


## 测试程序


def main() -> None:
    """CoreMemory 功能的完整测试程序。

    该函数模拟了CoreMemory的典型使用场景，包括初始化、添加记忆、检索记忆，
    并验证了记忆的持久化存储和唯一ID的生成。
    """
    import os
    import shutil

    # 允许重复的OpenMP运行时库，解决部分环境下的冲突
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    print("===== 开始 CoreMemory 功能测试 =====")

    # --- 测试准备：确保测试目录存在并清理旧数据 ---
    # 定义测试用的聊天历史目录
    test_chat_history_dir = Path("./chat_history/test_character")
    # 如果测试目录已存在，则先删除以确保测试环境的干净
    if test_chat_history_dir.exists():
        print(f"清理旧的测试目录: {test_chat_history_dir}")
        shutil.rmtree(test_chat_history_dir)
    # 创建测试目录及其父目录
    test_chat_history_dir.mkdir(parents=True, exist_ok=True)
    print("√ 测试环境准备就绪")

    # --- 模拟配置加载 ---
    # 创建一个模拟的XnneHangLabSettings对象
    settings_mock = XnneHangLabSettings()  # type: ignore 加载默认配置
    # 确保角色名称与测试目录名称匹配
    settings_mock.agent.system_prompt_name = "test_character"
    settings_mock.agent.memory.books_thresholds = 0.5  # 设定一个阈值用于测试
    settings_mock.agent.memory.scan_depth = 5  # 设定扫描深度

    # === 测试1：初始化新记忆系统 ===
    print("\n--- 测试1：初始化新记忆系统 ---")
    # 第一次初始化CoreMemory，此时core_mem.yml文件应该不存在
    # 直接将模拟的settings_mock传入CoreMemory的构造函数
    memory = CoreMemory(config_settings=settings_mock)
    print("√ 记忆系统初始化成功")
    # 验证初始记忆文件的存在
    assert memory.memory_file_path.exists(), "记忆文件core_mem.yml应已创建"
    # 验证初始记忆数量至少为1（因为会添加一条默认记忆）
    assert len(memory.raw_memory_texts) >= 1, "初始记忆数量应至少为1"
    assert "第一次与用户相遇" in memory.raw_memory_texts[0], "初始记忆内容不正确"
    assert memory.faiss_index.ntotal == len(memory.raw_memory_texts), "FAISS索引的向量数量与原始记忆文本数量不匹配"
    print(f"初始记忆数量: {len(memory.raw_memory_texts)}")
    print(f"第一条记忆内容: {memory.raw_memory_texts[0]}")

    # === 测试2：添加新记忆 ===
    print("\n--- 测试2：添加新记忆 ---")
    new_memories_to_add = ["用户喜欢蓝色和绿色", "用户养了一只叫小花的猫", "用户的生日是5月20日"]
    initial_memory_count = len(memory.raw_memory_texts)
    memory.add_memory(new_memories_to_add)
    print(f"添加后记忆数量: {len(memory.raw_memory_texts)}")
    # 验证记忆数量是否正确增加
    assert len(memory.raw_memory_texts) == initial_memory_count + len(new_memories_to_add), "记忆数量未正确增加"
    # 验证新添加的记忆是否包含在内
    assert "用户养了一只叫小花的猫" in memory.raw_memory_texts, "新记忆未成功添加"
    assert memory.faiss_index.ntotal == len(memory.raw_memory_texts), "FAISS索引的向量数量未随新记忆更新"
    print(f"最新添加记忆: {memory.raw_memory_texts[-1]}")

    # === 测试3：记忆检索功能 ===
    print("\n--- 测试3：记忆检索功能 ---")

    # 子测试3.1：精确匹配检索
    print("\n子测试3.1：精确匹配检索")
    # 查询“猫”，预期能检索到关于猫的记忆
    retrieved_results_cat = memory.find_memory("猫", retrieval_limit=1)
    print("检索'猫'的结果:")
    for res in retrieved_results_cat:
        print(f" - {res}")  # 打印部分内容，避免过长输出
    assert len(retrieved_results_cat) > 0, "检索'猫'应返回结果"
    assert any("小花的猫" in r for r in retrieved_results_cat), "检索'猫'未返回预期的猫相关记忆"
    assert isinstance(retrieved_results_cat[0], str), "检索结果的元素类型应为字符串"

    # 子测试3.2：语义相似检索
    print("\n子测试3.2：语义相似检索")
    # 查询“颜色偏好”，预期能检索到关于“用户喜欢蓝色和绿色”的记忆
    retrieved_results_color = memory.find_memory("颜色偏好", retrieval_limit=1)
    print("检索'颜色偏好'的结果:")
    for res in retrieved_results_color:
        print(f" - {res}")
    assert len(retrieved_results_color) > 0, "检索'颜色偏好'应返回结果"
    assert any("蓝色和绿色" in r for r in retrieved_results_color), "检索'颜色偏好'未返回预期的颜色相关记忆"

    # 子测试3.3：无相关结果
    print("\n子测试3.3：无相关结果")
    # 查询一个不相关的词，预期不返回任何结果（或少于阈值）
    retrieved_results_mars = memory.find_memory("火星探索计划", retrieval_limit=1)
    print(f"无相关结果时返回数量: {len(retrieved_results_mars)}")
    # 注意：这里不能简单断言 len == 0，因为即使不相关也可能因为FAISS的最近邻查找返回结果，但相似度会很低。
    # 更好的断言是检查相似度是否低于阈值（如果可以获取到内部相似度数据）。
    # 对于这个测试，我们先假设不相关应该返回空列表。
    assert len(retrieved_results_mars) == 0, "检索'火星探索计划'时不应返回相关结果"  # 调整为严格断言

    # === 测试4：持久化存储验证 ===
    print("\n--- 测试4：持久化存储验证 ---")
    print("创建新实例验证数据加载...")
    # 销毁旧的memory实例，确保是从文件重新加载
    del memory
    # 创建一个新的CoreMemory实例，它应该从文件中加载之前添加的记忆
    # 同样，传入模拟的settings_mock以确保路径正确
    memory2 = CoreMemory(config_settings=settings_mock)
    print(f"加载的记忆数量: {len(memory2.raw_memory_texts)}")
    print(f"最后一条记忆: {memory2.raw_memory_texts[-1]}")
    # 验证新实例加载的记忆数量和内容是否正确
    assert len(memory2.raw_memory_texts) == initial_memory_count + len(new_memories_to_add), (
        "新实例加载的记忆数量不正确"
    )
    assert "用户养了一只叫小花的猫" in memory2.raw_memory_texts, "新实例未正确加载之前添加的记忆"
    assert memory2.faiss_index.ntotal == len(memory2.raw_memory_texts), "新实例的FAISS索引向量数量不匹配"

    # === 测试5：唯一ID生成 ===
    print("\n--- 测试5：唯一ID生成 ---")
    print("生成10个新ID测试唯一性:")
    generated_ids: list[str] = []
    for _ in range(10):
        # 直接调用内部方法进行测试
        new_generated_id = memory2._generate_unique_id()  # type: ignore
        print(f"生成ID: {new_generated_id}")
        generated_ids.append(new_generated_id)
    # 验证生成的ID是否都是唯一的
    assert len(set(generated_ids)) == 10, "生成的ID不唯一"
    print(f"唯一性验证: {len(set(generated_ids)) == 10}")

    print("\n===== 所有测试通过! =====")

    # # --- 清理测试环境 ---
    # print("\n清理测试环境...")
    # if test_chat_history_dir.exists():
    #     shutil.rmtree(test_chat_history_dir)
    # print("√ 测试环境清理完毕")


if __name__ == "__main__":
    main()
