from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import faiss
import shortuuid
import yaml

from lab.agent.memory import embedding
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class CoreMemory:
    """核心记忆系统，负责长期记忆的存储和检索"""

    def _load_configuration(self) -> None:
        """重新加载配置文件设置"""
        self.character_name: str = self.config.agent.system_prompt_name
        self.user_name: str = "xnnehang"
        self.similarity_threshold: float = 0.5  # 相似度阈值，用于记忆检索
        self.memory_file: Path = Path(f"./chat_history/{self.character_name}/core_mem.yml")

    def __init__(self) -> None:
        # 初始化记忆系统
        self.config: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)
        self._load_configuration()

        # 记忆存储相关数据结构
        self.memory_records: list[str] = []  # 原始记忆文本
        self.text_contents: list[str] = []  # 带时间戳的完整记忆内容
        self.uuids: list[str] = []  # 唯一标识符列表

        # 初始化文件存储路径
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)

        if self.memory_file.exists():
            self._load_existing_memories()
        else:
            self._initialize_new_memory_file()

        # 创建FAISS索引
        vectors: NDArray[np.float32] = embedding.t2vect(self.memory_records)
        self.faiss_index: faiss.IndexFlatIP = faiss.IndexFlatIP(vectors.shape[1])
        self.faiss_index.add(vectors)  # type: ignore

    def _load_existing_memories(self) -> None:
        """加载已存在的记忆文件"""
        with self.memory_file.open("r", encoding="utf-8") as f:
            data: dict[str, dict[str, Any]] = yaml.safe_load(f) or {}
            for uuid, record in data.items():
                self.memory_records.append(record["text"])
                self.text_contents.append(f"记忆获取时间：{record['time']}\n{record['text']}")
                self.uuids.append(uuid)

    def _initialize_new_memory_file(self) -> None:
        """初始化新的记忆文件"""
        # 创建带有警告头的空文件
        with self.memory_file.open("a", encoding="utf-8") as f:
            f.write("\n\n# 核心记忆文件，请勿自行修改！否则会丢失索引！\n\n")

        # 添加初始记忆条目
        timestamp: str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        initial_text: str = "第一次相遇"
        new_uuid: str = self._generate_unique_id()

        initial_record: dict[str, dict[str, Any]] = {new_uuid: {"time": timestamp, "text": initial_text}}

        # 写入并重新加载数据
        with self.memory_file.open("a", encoding="utf-8") as f:
            yaml.safe_dump(initial_record, f, allow_unicode=True)

        self._load_existing_memories()

    def _generate_unique_id(self) -> str:
        """生成唯一标识符"""
        while (new_uuid := shortuuid.ShortUUID().random(length=10)) in self.uuids:
            continue
        return new_uuid

    def find_memory(self, query: str, result_container: list[str]) -> list[str]:
        """
        根据查询文本检索相关记忆

        Args:
            query: 需要检索的文本
            result_container: 用于存储检索结果的列表
        """
        query_vector: NDArray[np.float32] = embedding.t2vect([query])
        distances: NDArray[np.float32]
        indices: NDArray[np.int64]

        # FAISS相似度搜索
        distances, indices = self.faiss_index.search(query_vector, 5)  # type: ignore

        relevant_memories: list[str] = []
        for distance_row, index_row in zip(distances, indices, strict=True):  # type: ignore
            for distance, idx in zip(distance_row, index_row, strict=True):
                if distance >= self.similarity_threshold:
                    relevant_memories.append(self.text_contents[idx])  # type: ignore

        if relevant_memories:
            result_container.extend(relevant_memories)
        return result_container # 虽然是个指针，但返回一下比较容易明白意图

    def add_memory(self, new_memories: list[str]) -> None:
        """
        添加新的记忆内容

        Args:
            new_memories: 需要添加的记忆文本列表
        """
        records_to_add: dict[str, dict[str, Any]] = {}

        for memory_text in new_memories:
            new_uuid: str = self._generate_unique_id()
            timestamp: str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            records_to_add[new_uuid] = {"time": timestamp, "text": memory_text}

            self.memory_records.append(memory_text)
            self.text_contents.append(f"记忆获取时间：{timestamp}\n{memory_text}")

        # 追加写入文件
        with self.memory_file.open("a", encoding="utf-8") as f:
            yaml.safe_dump(records_to_add, f, allow_unicode=True)

        # 更新FAISS索引
        new_vectors: NDArray[np.float32] = embedding.t2vect(new_memories)
        self.faiss_index.add(new_vectors)  # type: ignore

        print(f"[系统提示] 已添加核心记忆：{new_memories}")

# 看起来目前似乎每次重启应用都会根据 core_memory(文本重新计算 vector 然后存入内存好像还会重构索引).
# 实际上 sentence embedding 的结果，对于一条输入和多条输入时不影响的，简单来说不会因为是同批次的输入就会关联度更高离得更近。
# 这样的设计一定程度上简化掉了向量数据库的工作，学习成本变低了，在几百几千条上速度应该完全可以容忍，毕竟 embedding 那边是一次性输出的，而不是 for 级别的输出、
# 如果用 gpu 来计算 embedding, 那么应该延迟还是在毫秒和秒级的。对于我们目前的情况来说是恰好的。暂时不需要考虑向量数据库。
