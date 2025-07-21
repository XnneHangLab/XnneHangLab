from __future__ import annotations

import os
import pickle
import shutil
import time
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import jionlp as jio
import numpy as np
import requests
import yaml
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from lab.agent.memory import embedding
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.utils.TxtHelper import read_prompt_from_text_file

if TYPE_CHECKING:
    from numpy.typing import NDArray


class LongTermMemory:
    """长期记忆管理系统，负责记忆的存储、检索和持久化。

    该类通过将对话记录按天存储在YAML文件中来管理长期记忆。
    为了加速检索，它为每条记忆的“标签”生成向量嵌入，并将这些向量缓存到pickle文件中。
    它支持基于时间和基于语义相似度的两种记忆检索方式。
    """

    def __init__(self, config: XnneHangLabSettings | None = None) -> None:
        """初始化长期记忆系统。

        Args:
            config: 一个可选的配置对象。如果未提供，将从默认文件加载。
        """
        # 如果提供了配置，则使用它；否则从文件加载
        self.config = config if config is not None else load_settings_file("lab.toml", XnneHangLabSettings)
        # 从配置初始化记忆相关属性
        self._init_memory_attributes()

        # 定义并创建记忆存储的根目录
        self.memory_dir = Path(f"./chat_history/{self.char_name}/memorys")
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 初始化用于存储记忆数据的数据结构
        self.timestamp_keys: list[int] = []  # 按时间排序的记忆时间戳列表（Unix秒）
        self.memory_records: dict[int, str] = {}  # 字典：{时间戳: 记忆文本}
        self.tag_vectors: NDArray[np.float32] | None = None  # 记忆标签的向量化表示

        # 从磁盘加载已存在的记忆
        self._load_existing_memories()

    def _init_memory_attributes(self) -> None:
        """从配置对象中加载和设置记忆系统的属性。"""
        self.char_name: str = self.config.agent.system_prompt_name  # AI角色名称
        self.user_name: str = "xnnehang"  # 默认的用户名
        self.similarity_threshold: float = self.config.agent.memory.mem_thresholds  # 语义搜索的相似度阈值
        self.enable_semantic_check: bool = self.config.agent.memory.enable_check_memorys  # 是否启用语义相似度检查

    def _load_existing_memories(self) -> None:
        """从磁盘加载所有已存在的记忆YAML文件和对应的向量缓存。"""
        # 获取所有记忆YAML文件并按文件名（日期）排序
        memory_files = sorted(self.memory_dir.glob("*.yaml"))
        if not memory_files:
            print("[系统] 未找到任何现有记忆文件。")
            # 修复：将维度从 128 修改为 768。这是错误的主要来源。
            self.tag_vectors = np.empty((0, 768), dtype=np.float32)
            return

        # all_vectors: list[NDArray[np.float32]] = []
        all_tags_for_embedding: list[str] = []
        temp_records: list[tuple[int, str, str]] = []  # (timestamp, tag, message)

        # 第一遍：读取所有YAML，收集记录和标签
        for mem_file in memory_files:
            try:
                with mem_file.open("r", encoding="utf-8") as f:
                    records: dict[int, Any] = yaml.safe_load(f) or {}
                for ts, data in records.items():
                    tag = data.get("text_tag", "")
                    msg = (
                        str(data.get("msg", "")).replace("{{user}}", self.user_name).replace("{{char}}", self.char_name)
                    )
                    temp_records.append((ts, tag, msg))
            except (yaml.YAMLError, OSError) as e:
                print(f"[错误] 加载或解析记忆文件失败: {mem_file}\n{e}")

        # 按时间戳排序所有记录
        temp_records.sort(key=lambda x: x[0])

        # 填充内存数据结构
        for ts, tag, msg in temp_records:
            self.timestamp_keys.append(ts)
            self.memory_records[ts] = msg
            all_tags_for_embedding.append(tag)

        # 第二遍：处理向量
        vector_file = self.memory_dir / "all_vectors.pkl"
        if vector_file.exists() and len(all_tags_for_embedding) > 0:
            try:
                with vector_file.open("rb") as f:
                    self.tag_vectors = pickle.load(f)
                # 校验向量数量和维度是否匹配
                if (
                    self.tag_vectors is not None
                    and len(self.tag_vectors) == len(all_tags_for_embedding)
                    and self.tag_vectors.shape[1] == 768
                ):  # 修复：增加维度校验
                    print(f"[成功] 从 {vector_file.name} 加载了 {len(self.tag_vectors)} 个向量缓存。")
                else:
                    print("[警告] 向量缓存与记忆记录不匹配（数量或维度错误），将重新生成。")
                    self.tag_vectors = None  # 标记为无效以便重新生成
            except (pickle.PickleError, OSError) as e:
                print(f"[错误] 加载向量缓存失败: {e}。将重新生成。")
                self.tag_vectors = None

        # 如果需要，重新生成向量
        if self.tag_vectors is None and all_tags_for_embedding:
            print(f"[处理中] 正在为 {len(all_tags_for_embedding)} 条记忆生成向量...")
            self.tag_vectors = embedding.t2vect(all_tags_for_embedding).astype(np.float32)
            self._save_all_vectors_cache()

        elif self.tag_vectors is None:
            # 修复：将维度从 128 修改为 768
            self.tag_vectors = np.empty((0, 768), dtype=np.float32)

        print(f"[完成] 共加载 {len(self.timestamp_keys)} 条记忆。")

    def _save_all_vectors_cache(self) -> None:
        """将所有向量一次性保存到单个缓存文件中。"""
        if self.tag_vectors is None or self.tag_vectors.size == 0:
            return
        vector_file = self.memory_dir / "all_vectors.pkl"
        try:
            with vector_file.open("wb") as f:
                pickle.dump(self.tag_vectors, f)
            print(f"[完成] 已将所有向量缓存到: {vector_file.name}")
        except OSError as e:
            print(f"[错误] 保存全局向量缓存失败: {e}")

    def find_time_range(self, start_ts: int, end_ts: int) -> tuple[int, int] | None:
        """使用二分查找在排序的时间戳列表中定位时间范围对应的索引。

        Args:
            start_ts: 开始时间戳（Unix秒）。
            end_ts: 结束时间戳（Unix秒）。

        Returns:
            一个包含左右索引的元组 (left, right)，如果范围内无数据则返回 None。
        """
        left = bisect_left(self.timestamp_keys, start_ts)
        right = bisect_right(self.timestamp_keys, end_ts)
        return (left, right - 1) if right > left else None

    def get_memorys(self, msg: str, result_list: list[str], time_node: str) -> list[str]:
        """根据输入文本和时间节点，检索相关的记忆。

        Args:
            msg: 用户的查询文本。
            result_list: 用于追加结果的列表（此设计模式欠佳，但保留原逻辑）。
            time_node: 当前对话的时间基点（例如 "2025-07-21 17:00:00"）。

        Returns:
            更新后的结果列表。
        """
        if not self.timestamp_keys:
            return []

        time_spans = self._extract_time_spans(msg, time_node)
        if not time_spans:
            return []

        start_idx, end_idx = time_spans
        # 根据配置决定使用语义搜索还是直接范围搜索
        if self.enable_semantic_check:
            return self._semantic_search(msg, start_idx, end_idx, result_list)
        return self._direct_search(start_idx, end_idx, result_list)

    def _extract_time_spans(self, msg: str, time_node: str) -> tuple[int, int] | None:
        """从文本中提取时间实体，并转换为记忆索引范围。"""
        try:
            # jio.ner.extract_time 用于从文本中识别人类语言描述的时间
            time_entities: list[dict] = jio.ner.extract_time(  # type: ignore
                f"[{time_node}]{msg}", time_base=time.time(), with_parsing=False
            )
        except Exception as e:
            print(f"[错误] jio.ner.extract_time 调用失败: {e}")
            return None

        if not time_entities or len(time_entities) < 2:  # type: ignore
            return None

        time_spans_ts: list[int] = []
        for entity in time_entities[1:]:  # type:ignore 第一个实体是基准时间，跳过
            try:
                # jio.parse_time 将识别出的时间文本（如“昨天”）解析为标准时间格式
                parsed_time: dict = jio.parse_time(entity["text"], time_base=time_entities[0]["text"])  # type: ignore
                start_str, end_str = parsed_time["time"]  # type: ignore
                start_ts = int(time.mktime(time.strptime(start_str, "%Y-%m-%d %H:%M:%S")))  # type: ignore
                end_ts = int(time.mktime(time.strptime(end_str, "%Y-%m-%d %H:%M:%S")))  # type: ignore
                time_spans_ts.extend([start_ts, end_ts])
            except (KeyError, TypeError, ValueError) as e:
                print(f"[错误] 时间解析失败: {entity['text']} -> {e}")

        if not time_spans_ts:
            return None

        # 返回包含此时间范围的记忆在列表中的起始和结束索引
        return self.find_time_range(min(time_spans_ts), max(time_spans_ts))

    def _semantic_search(self, msg: str, start: int, end: int, result: list[str]) -> list[str]:
        """在指定时间范围内执行基于语义相似度的记忆检索。"""
        print(f"[提示] 深度检索记忆，阈值：{self.similarity_threshold}")
        if self.tag_vectors is None or self.tag_vectors.size == 0:
            return result

        query_vector: NDArray[np.float32] = embedding.t2vect([msg])[0]
        relevant_memories: list[str] = []

        # 提取该时间范围内的向量进行计算
        target_vectors = self.tag_vectors[start : end + 1]

        # 计算查询向量与目标向量的点积（余弦相似度）
        similarities = np.dot(target_vectors, query_vector)

        # 筛选出超过阈值的记忆
        for i, similarity in enumerate(similarities):
            if similarity >= self.similarity_threshold:
                memory_index = start + i
                relevant_memories.append(self.memory_records[self.timestamp_keys[memory_index]])

        if relevant_memories:
            result.append("\n".join(relevant_memories))

        return result

    def _direct_search(self, start: int, end: int, result: list[str]) -> list[str]:
        """直接返回指定时间范围内的所有记忆。"""
        memories = [self.memory_records[self.timestamp_keys[idx]] for idx in range(start, end + 1)]
        if memories:
            result.append("\n".join(memories))
        return result

    def add_memory(self, memory_data: dict[str, Any]) -> None:
        """添加一条新的记忆，并更新存储和向量缓存。"""
        timestamp: int = int(memory_data["t_n"])
        text_tag: str = memory_data["text_tag"]
        message: str = memory_data["msg"]

        # 更新内存中的数据结构
        # 使用 bisect_left 找到新记忆应该插入的位置以保持有序
        insert_pos = bisect_left(self.timestamp_keys, timestamp)
        self.timestamp_keys.insert(insert_pos, timestamp)
        self.memory_records[timestamp] = message

        # 更新向量
        tag_vector: NDArray[np.float32] = embedding.t2vect([text_tag]).astype(np.float32)
        if self.tag_vectors is not None:
            self.tag_vectors = np.insert(self.tag_vectors, insert_pos, tag_vector, axis=0)
        else:  # 如果是第一条记忆
            self.tag_vectors = np.array([tag_vector], dtype=np.float32)

        # 将新向量和所有其他向量一起保存到全局缓存中
        self._save_all_vectors_cache()

        # 持久化到YAML文件
        time_struct = time.localtime(timestamp)
        date_str = f"{time_struct.tm_year}-{time_struct.tm_mon:02d}-{time_struct.tm_mday:02d}"
        yaml_file = self.memory_dir / f"{date_str}.yaml"

        # 使用 ruamel.yaml 以追加模式写入，并保持格式（特别是多行字符串）
        yaml_serializer = YAML()
        yaml_serializer.preserve_quotes = True
        yaml_serializer.width = 4096

        # 读取现有文件内容，或创建新字典
        if yaml_file.exists():
            with yaml_file.open("r", encoding="utf-8") as f:
                day_records = yaml_serializer.load(f) or {}  # type: ignore
        else:
            day_records = {}

        # 添加新记录并按时间戳排序
        day_records[timestamp] = {"text_tag": text_tag, "msg": LiteralScalarString(message)}
        sorted_day_records = dict(sorted(day_records.items()))  # type: ignore

        # 写回文件
        with yaml_file.open("w", encoding="utf-8") as f:
            yaml_serializer.dump(sorted_day_records, f)  # type: ignore

    # 此方法依赖外部服务和特定数据结构，在单元测试中通常会被模拟
    def add_memory1(self, data: list[dict[str, str]], t_n: int, llm_config: dict[str, str]) -> None:
        """通过LLM提取对话摘要作为记忆标签，并记录长期记忆。"""
        # 读取用于生成记忆标签的系统提示
        mmsg = read_prompt_from_text_file("memory_assistant")
        res_msg = "用户：" + data[-2]["content"]
        res_body = {
            "model": llm_config["model"],
            "messages": [{"role": "system", "content": mmsg}, {"role": "user", "content": res_msg}],
        }
        key = llm_config["key"]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        res_tag = "日常闲聊"  # 默认标签

        try:
            # 向大模型API发送请求
            res = requests.post(llm_config["api"], json=res_body, headers=headers, timeout=15)
            res.raise_for_status()  # 如果请求失败则抛出异常
            content = res.json()["choices"][0]["message"]["content"]
            # 清理API返回的文本
            cleaned_content = jio.remove_html_tag(content).replace(" ", "").replace("\n", "")  # type: ignore
            print(f"[记录日记结果]【{cleaned_content}】")
            # 如果不是“日常闲聊”，则使用API返回的结果作为标签
            if "日常闲聊" not in cleaned_content:
                res_tag = cleaned_content
        except requests.RequestException as e:
            print(f"【错误】请求LLM API失败: {e}")
        except (KeyError, IndexError) as e:
            print(f"【错误】解析LLM API响应失败: {e}")

        t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t_n))
        user_msg = data[-2]["content"]
        char_msg = data[-1]["content"]

        # 组装记忆数据
        m_data = {
            "t_n": t_n,
            "text_tag": res_tag,
            "msg": f"时间：{t_str}\n{{user}}：{user_msg}\n{{char}}：{char_msg}",
        }
        self.add_memory(m_data)


## ==================== 测试程序 ====================


def main() -> None:
    """LongTermMemory 功能的完整测试程序。"""

    # 允许重复的OpenMP运行时库，解决部分环境下的冲突
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    print("===== 开始 LongTermMemory 功能测试 =====")

    # --- 测试准备：确保测试目录存在并清理旧数据 ---
    test_char_name = "test_longterm_char"
    test_memory_dir = Path(f"./chat_history/{test_char_name}")
    if test_memory_dir.exists():
        print(f"清理旧的测试目录: {test_memory_dir}")
        shutil.rmtree(test_memory_dir)
    print("√ 测试环境准备就绪")

    # --- 模拟配置加载 ---
    settings_mock = XnneHangLabSettings()  # type: ignore
    settings_mock.agent.system_prompt_name = test_char_name

    # === 测试1：初始化空的记忆系统 ===
    print("\n--- 测试1：初始化空的记忆系统 ---")
    lt_memory = LongTermMemory(config=settings_mock)
    print("√ 记忆系统初始化成功")
    assert lt_memory.memory_dir.exists(), "记忆目录应已创建"
    assert len(lt_memory.timestamp_keys) == 0, "新系统的记忆时间戳应为空"
    assert lt_memory.tag_vectors is not None and lt_memory.tag_vectors.shape[0] == 0, "新系统的向量组应为空"

    # === 测试2：添加新记忆 ===
    print("\n--- 测试2：添加新记忆 ---")
    ts1 = int(time.time()) - 86400  # 昨天
    ts2 = int(time.time()) - 3600  # 1小时前
    ts3 = int(time.time())  # 现在

    memories_to_add = [
        {
            "t_n": ts1,
            "text_tag": "关于宠物的讨论",
            "msg": f"时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts1))}\n{{user}}：你喜欢猫还是狗？\n{{char}}：我喜欢会运行代码的机器狗。",
        },
        {
            "t_n": ts2,
            "text_tag": "关于颜色的偏好",
            "msg": f"时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts2))}\n{{user}}：你最喜欢的颜色是什么？\n{{char}}：我喜欢终端的绿色。",
        },
        {
            "t_n": ts3,
            "text_tag": "未来的计划",
            "msg": f"时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts3))}\n{{user}}：你明天有什么计划？\n{{char}}：学习新的算法。",
        },
    ]

    for mem in memories_to_add:
        lt_memory.add_memory(mem)

    print(f"添加后记忆数量: {len(lt_memory.timestamp_keys)}")
    assert len(lt_memory.timestamp_keys) == 3, "记忆数量应为3"
    assert lt_memory.tag_vectors is not None and len(lt_memory.tag_vectors) == 3, "向量数量应为3"
    assert lt_memory.timestamp_keys == sorted(lt_memory.timestamp_keys), "时间戳应保持排序"

    # 验证文件是否创建
    date_str_yesterday = time.strftime("%Y-%m-%d", time.localtime(ts1))
    expected_yesterday_path = lt_memory.memory_dir / f"{date_str_yesterday}.yaml"
    expected_all_vectors_path = lt_memory.memory_dir / "all_vectors.pkl"
    assert expected_yesterday_path.exists(), f"昨天的记忆YAML文件应存在, {str(expected_yesterday_path)}"
    assert (expected_all_vectors_path).exists(), f"全局向量缓存文件应存在, {expected_all_vectors_path}"
    print("√ 添加记忆并创建文件成功")

    # === 测试3：持久化存储验证 ===
    print("\n--- 测试3：持久化存储验证 ---")
    print("创建新实例验证数据加载...")
    del lt_memory

    lt_memory2 = LongTermMemory(config=settings_mock)
    print(f"重新加载的记忆数量: {len(lt_memory2.timestamp_keys)}")
    assert len(lt_memory2.timestamp_keys) == 3, "新实例加载的记忆数量应为3"
    assert lt_memory2.timestamp_keys[0] == ts1, "加载的第一个时间戳不正确"
    assert "机器狗" in lt_memory2.memory_records[ts1], "加载的记忆内容不正确"
    assert lt_memory2.tag_vectors is not None and lt_memory2.tag_vectors.shape[0] == 3, "加载的向量数量应为3"
    print("√ 持久化加载成功")

    # === 测试4：记忆检索功能 ===
    print("\n--- 测试4：记忆检索功能 ---")

    # 子测试4.1: 直接时间范围检索
    print("\n子测试4.1: 直接时间范围检索")
    lt_memory2.enable_semantic_check = False
    with (
        patch("jionlp.ner.extract_time", return_value=[{"text": "mock_base"}, {"text": "昨天"}]),
        patch(
            "jionlp.parse_time",
            return_value={
                "time": [
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts1 - 100)),
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts1 + 100)),
                ]
            },
        ),
    ):
        results = lt_memory2.get_memorys("检索昨天的对话", [], time.strftime("%Y-%m-%d %H:%M:%S"))

    assert len(results) == 1, "直接时间检索应返回1条记录"
    assert "机器狗" in results[0], "直接时间检索返回了错误的记录"
    print("√ 直接时间范围检索成功")

    # 子测试4.2: 语义检索
    print("\n子测试4.2: 语义检索")
    lt_memory2.enable_semantic_check = True

    # 模拟 embedding 函数，使得查询和特定文档有高相似度
    # def selective_t2vect(texts: list[str]) -> NDArray[np.float32]:
    #     vectors = []
    #     for text in texts:
    #         # 修复：将维度从 128 修改为 768
    #         vec = np.random.rand(1, 768).astype(np.float32)
    #         if "宠物" in text:
    #             vec[0, :10] = 0.9  # 为“宠物”相关的查询和文档设置高相似度特征
    #         else:
    #             vec[0, :10] = 0.1
    #         vectors.append(vec)
    #     return np.vstack(vectors)

    # 用我们的选择性模拟函数替换全局模拟函数
    # embedding.t2vect.side_effect = selective_t2vect
    # 重新加载记忆以应用新的 embedding 逻辑
    del lt_memory2
    lt_memory3 = LongTermMemory(config=settings_mock)

    with (
        patch("jionlp.ner.extract_time", return_value=[{"text": "mock_base"}, {"text": "过去两天"}]),
        patch(
            "jionlp.parse_time",
            return_value={
                "time": [
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts1 - 100)),
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts3 + 100)),
                ]
            },
        ),
    ):
        results_semantic = lt_memory3.get_memorys("聊聊关于宠物的话题", [], time.strftime("%Y-%m-%d %H:%M:%S"))

    print(f"语义检索结果: {results_semantic}")
    assert len(results_semantic) > 0, "语义检索应返回结果"
    assert "机器狗" in results_semantic[0], "语义检索应找到关于宠物的记忆"
    print("√ 语义检索成功")

    print("\n===== 所有测试通过! =====")

    # --- 清理测试环境 ---
    print("\n清理测试环境...")
    if test_memory_dir.exists():
        shutil.rmtree(test_memory_dir)
    print("√ 测试环境清理完毕")


if __name__ == "__main__":
    main()
