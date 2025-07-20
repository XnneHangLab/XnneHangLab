from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

# from typing import Literal
import hnswlib
import numpy as np
import yaml
from numpy.typing import NDArray

from lab.agent.memory import embedding
from lab.config_manager import XnneHangLabSettings, load_settings_file


def calculate_file_md5(file_path: Path) -> str:
    """计算文件的MD5校验和

    Args:
        file_path: 需要计算的文件路径对象

    Returns:
        16进制格式的MD5哈希字符串
    """
    md5_hash = hashlib.md5()
    with file_path.open("rb") as file:
        while True:
            data_chunk = file.read(4096)
            if not data_chunk:
                break
            md5_hash.update(data_chunk)
    return md5_hash.hexdigest()


class DataBase:
    """长期记忆存储系统，负责知识库的向量化存储和相似性检索

    Attributes:
        knowledge_embeddings: 所有知识文本的向量集合
        knowledge_texts: 对应的原始知识文本
        search_index: 用于快速检索的向量索引
    """

    def _load_configuration(self) -> None:
        """加载应用配置并初始化路径设置"""
        self.settings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.similarity_threshold = float(self.settings.agent.memory.books_thresholds)
        self.max_retrieve_count = int(self.settings.agent.memory.scan_depth)
        character_name = self.settings.agent.system_prompt_name
        self.data_directory = Path(f"./chat_history/{character_name}/data_base")

    def __init__(self) -> None:
        """初始化记忆数据库，自动加载并向量化知识库文件"""
        self._load_configuration()
        self.knowledge_texts: list[str] = []

        # 初始化缓存目录
        cache_dir = self.data_directory / "tmp/labels"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 加载已有的MD5校验记录
        md5_records: dict[str, str] = self._load_md5_records(cache_dir)

        # 识别需要更新的知识库文件
        new_books, book_paths = self._detect_new_books(md5_records)

        # 处理新增或修改的知识文件
        self._process_new_books(new_books, book_paths, cache_dir, md5_records)

        # 构建向量索引
        embedding_arrays = self._load_cached_embeddings(cache_dir)
        self._build_vector_index(embedding_arrays)

    def _load_md5_records(self, cache_dir: Path) -> dict[str, str]:
        """加载已有的MD5校验记录文件

        Args:
            cache_dir: 缓存目录路径对象

        Returns:
            文件名到MD5哈希的映射字典
        """
        md5_file = cache_dir / "label.yaml"
        try:
            with md5_file.open("r", encoding="utf-8") as f:
                records = yaml.safe_load(f) or {}  # type: ignore[reportOptionalMemberAccess] if yaml.safe_load(f) is None else {}, 学会了一个新写法 =-=.
        except FileNotFoundError:
            records = {}
        return records  # type: ignore[return-value]

    def _detect_new_books(self, existing_records: dict[str, str]) -> tuple[list[str], list[Path]]:
        """检测需要更新的知识库文件

        Args:
            existing_records: 现有的MD5记录

        Returns:
            (新增文件名列表, 对应的文件路径列表)
        """
        new_files: list[str] = []
        file_paths: list[Path] = []
        for file in self.data_directory.iterdir():
            if file.is_file():
                current_md5 = calculate_file_md5(file)
                if file.name not in existing_records or existing_records[file.name] != current_md5:
                    new_files.append(file.name)
                    file_paths.append(file)
        return new_files, file_paths

    def _process_new_books(
        self, new_books: list[str], book_paths: list[Path], cache_dir: Path, md5_records: dict[str, str]
    ) -> None:
        """处理新增或修改的知识文件

        Args:
            new_books: 新增文件名列表
            book_paths: 对应的文件路径列表
            cache_dir: 缓存目录路径
            md5_records: MD5记录字典
        """
        for idx, book_name in enumerate(new_books):
            book_path = book_paths[idx]
            try:
                with book_path.open("r", encoding="utf-8") as f:
                    book_data = yaml.safe_load(f)  # type: ignore[reportOptionalMemberAccess]

                # 准备向量化数据
                keys, values = zip(*book_data.items(), strict=True) if book_data else ([], [])
                embeddings = embedding.t2vect(list(keys))

                # 缓存处理结果
                cache_file = cache_dir / f"{book_name}.pkl"
                with cache_file.open("wb") as f:
                    pickle.dump({"embeddings": embeddings, "texts": values}, f)

                print(f"[系统] 成功向量化知识库【{book_name}】，加载{len(keys)}条数据")
                md5_records[book_name] = calculate_file_md5(book_path)
            except Exception as e:
                print(f"[错误] 知识库[{book_name}]加载失败: {str(e)}")
                md5_records[book_name] = calculate_file_md5(book_path)

        # 更新MD5记录文件
        with (cache_dir / "label.yaml").open("w") as f:
            yaml.safe_dump(md5_records, f)

    def _load_cached_embeddings(self, cache_dir: Path) -> list[NDArray[np.float32]]:
        """加载所有缓存的向量数据

        Args:
            cache_dir: 缓存目录路径

        Returns:
            包含所有向量数据的数组列表
        """
        embedding_arrays = []
        for cache_file in cache_dir.glob("*.pkl"):
            with cache_file.open("rb") as f:
                cached_data = pickle.load(f)
                embedding_arrays.append(cached_data["embeddings"].astype(np.float32))
                self.knowledge_texts.extend(cached_data["texts"])
                print(f"[系统] 加载缓存知识库【{cache_file.stem}】，共{len(cached_data['embeddings'])}条向量")

        # 处理空数据情况
        if not embedding_arrays:
            dummy_embedding = embedding.t2vect(["空数据填充"]).astype(np.float32)
            embedding_arrays.append(dummy_embedding)
            self.knowledge_texts.append("无有效知识数据")
        return embedding_arrays

    def _build_vector_index(self, embedding_arrays: list[NDArray[np.float32]]) -> None:
        """构建向量搜索索引

        Args:
            embedding_arrays: 需要建立索引的向量数组列表
        """
        combined_embeddings = np.concatenate(embedding_arrays)
        self.search_index = hnswlib.Index(space="cosine", dim=combined_embeddings.shape[1])
        self.search_index.init_index(max_elements=len(combined_embeddings), ef_construction=200, M=16)
        self.search_index.add_items(combined_embeddings)

    def retrieve_related_memory(self, query_texts: list[str]) -> str:
        """相似性检索接口

        Args:
            query_texts: 需要查询的文本列表

        Returns:
            拼接后的相关记忆文本
        """
        query_vectors = embedding.t2vect(query_texts).astype(np.float32)
        distances, indices = self.search_index.knn_query(query_vectors, k=self.max_retrieve_count)

        relevant_memories = []
        for query_idx in range(len(distances)):
            for result_idx in range(len(distances[query_idx])):
                if distances[query_idx][result_idx] >= self.similarity_threshold:
                    memory_text = self.knowledge_texts[indices[query_idx][result_idx]]
                    relevant_memories.append(memory_text)

        return "\n\n".join(relevant_memories)
