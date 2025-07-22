from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import TYPE_CHECKING

import faiss
import numpy as np
import yaml

from lab.agent.memory import embedding
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from numpy.typing import NDArray


def calculate_file_md5(file_path: Path) -> str:
    """Calculates the MD5 checksum of a given file.

    Args:
        file_path: The path object of the file to calculate the MD5 for.

    Returns:
        The MD5 hash string in hexadecimal format.
    """
    md5_hash = hashlib.md5()
    # Open the file in binary read mode
    with file_path.open("rb") as file:
        # Read the file in chunks to handle large files efficiently
        while True:
            data_chunk = file.read(4096)  # Read 4KB chunks
            if not data_chunk:
                break  # End of file
            md5_hash.update(data_chunk)
    return md5_hash.hexdigest()


class KnowledgeDataBase:
    """Long-term memory storage system responsible for vectorizing and retrieving knowledge base.

    This class manages the loading, vectorization, and similarity search of knowledge texts,
    using FAISS for efficient approximate nearest neighbor search. It also handles
    caching of vectorized data to avoid redundant processing.

    Attributes:
        knowledge_texts: A list of original knowledge texts.
        faiss_index: The FAISS index used for fast similarity retrieval of embeddings.
        similarity_threshold: The minimum similarity score for a memory to be considered relevant.
        max_retrieve_count: The maximum number of relevant memories to retrieve.
        data_directory: The base directory where knowledge base files are stored.
    """

    def __init__(self, config: XnneHangLabSettings | None = None) -> None:
        """Initializes the knowledge database, loading and vectorizing knowledge files automatically."""
        self.settings = config if config is not None else load_settings_file("lab.toml", XnneHangLabSettings)
        self._load_configuration()
        self.knowledge_texts: list[str] = []
        self.knowledge_embeddings: list[NDArray[np.float32]] = []
        self.faiss_index: faiss.IndexFlatIP

        # Define the cache directory for vectorized data and MD5 records
        self.cache_directory = self.data_directory / "tmp" / "labels"
        self.cache_directory.mkdir(parents=True, exist_ok=True)

        # Load existing MD5 checksum records to identify changed or new files
        md5_records: dict[str, str] = self._load_md5_records()

        # Identify knowledge base files that need to be processed (new or modified)
        new_or_modified_book_paths = self._detect_new_or_modified_books(md5_records)

        # Process these identified files: vectorize and cache their contents
        self._process_knowledge_books(new_or_modified_book_paths, md5_records)

        # Load all cached embeddings and their corresponding texts
        self._load_all_cached_data()

        # Build the FAISS vector index from all loaded embeddings
        self._build_vector_index()

    def _load_configuration(self) -> None:
        """Loads application configuration settings and initializes path settings."""
        # Type conversion for configuration values
        self.similarity_threshold = float(self.settings.agent.memory.books_thresholds)
        self.max_retrieve_count = int(self.settings.agent.memory.scan_depth)
        character_name = self.settings.agent.character_name
        # Set the directory where knowledge base files are expected
        self.data_directory = Path(f"./chat_history/{character_name}/data_base")

    def _load_md5_records(self) -> dict[str, str]:
        """Loads existing MD5 checksum records from the cache file.

        These records help in determining which knowledge base files have changed
        and need re-vectorization.

        Returns:
            A dictionary mapping file names to their MD5 hashes.
        """
        md5_record_file = self.cache_directory / "label.yaml"
        try:
            # Attempt to open and load the YAML file
            with md5_record_file.open("r", encoding="utf-8") as f:
                # Use safe_load to prevent arbitrary code execution
                # If the file is empty or malformed, default to an empty dictionary
                records = yaml.safe_load(f)
                if records is None:
                    return {}  # Ensure an empty dict if the file is empty
                return records
        except FileNotFoundError:
            # If the MD5 record file doesn't exist, it means no files have been cached yet
            return {}
        except Exception as e:
            # Handle other potential errors during file loading
            print(f"[错误] 加载MD5记录文件失败: {e}")
            return {}

    def _detect_new_or_modified_books(self, existing_records: dict[str, str]) -> list[Path]:
        """Detects knowledge base files that are new or have been modified.

        Compares the current MD5 checksum of files in the data directory with
        previously recorded MD5s.

        Args:
            existing_records: A dictionary of existing MD5 records (filename: md5_hash).

        Returns:
            A list of Path objects for knowledge base files that need processing.
        """
        new_or_modified_book_paths: list[Path] = []
        # Iterate over all files directly within the data directory
        for file_path in self.data_directory.iterdir():
            if file_path.is_file():
                current_md5 = calculate_file_md5(file_path)
                # Check if the file is new or its MD5 hash has changed
                if file_path.name not in existing_records or existing_records[file_path.name] != current_md5:
                    new_or_modified_book_paths.append(file_path)
        return new_or_modified_book_paths

    def _process_knowledge_books(self, book_paths: list[Path], md5_records: dict[str, str]) -> None:
        """Processes new or modified knowledge base files by vectorizing their content and caching results.

        Args:
            book_paths: A list of Path objects for knowledge base files to process.
            md5_records: The dictionary to update with new MD5 hashes.
        """
        for book_path in book_paths:
            try:
                # Load the YAML content from the knowledge book file
                with book_path.open("r", encoding="utf-8") as f:
                    book_data = yaml.safe_load(f)
                    if book_data is None:
                        book_data = {}  # Handle empty YAML files gracefully

                # Prepare data for vectorization: extract keys (questions/concepts) and values (answers/details)
                # Ensure book_data is treated as a dictionary
                keys: list[str] = []
                values: list[str] = []
                if isinstance(book_data, dict):
                    for key, value in book_data.items():  # type: ignore
                        keys.append(str(key))  # Ensure keys are strings # type: ignore
                        values.append(str(value))  # Ensure values are strings # type: ignore
                if not keys:  # Skip if there's no data to vectorize
                    print(f"[系统] 知识库【{book_path.name}】为空，跳过向量化。")
                    md5_records[book_path.name] = calculate_file_md5(book_path)
                    continue

                # Vectorize the keys (e.g., questions or concepts) using the embedding model
                # Ensure the output is a numpy array of float32 for FAISS compatibility
                embeddings: NDArray[np.float32] = embedding.t2vect(keys).astype(np.float32)

                # Cache the vectorized embeddings and corresponding texts
                cache_file_path = self.cache_directory / f"{book_path.name}.pkl"
                with cache_file_path.open("wb") as f:
                    pickle.dump({"embeddings": embeddings, "texts": values}, f)

                print(f"[系统] 成功向量化知识库【{book_path.name}】，加载{len(keys)}条数据")
                # Update the MD5 record for the processed file
                md5_records[book_path.name] = calculate_file_md5(book_path)
            except Exception as e:
                print(f"[错误] 知识库[{book_path.name}]加载或向量化失败: {e}")
                # Even if processing fails, record the MD5 to prevent repeated attempts on the same file
                md5_records[book_path.name] = calculate_file_md5(book_path)

        # After processing all new/modified files, update the main MD5 record file
        md5_record_file = self.cache_directory / "label.yaml"
        with md5_record_file.open("w", encoding="utf-8") as f:
            yaml.safe_dump(md5_records, f)

    def _load_all_cached_data(self) -> None:
        """Loads all cached vectorized data (embeddings and texts) into memory."""
        self.knowledge_embeddings = []  # Reset to ensure fresh load
        self.knowledge_texts = []  # Reset to ensure fresh load

        # Iterate through all pickle files in the cache directory
        for cache_file_path in self.cache_directory.glob("*.pkl"):
            try:
                with cache_file_path.open("rb") as f:
                    cached_data = pickle.load(f)
                    # Append loaded embeddings and texts to the respective lists
                    # Ensure embeddings are float32 for FAISS
                    self.knowledge_embeddings.append(cached_data["embeddings"].astype(np.float32))
                    self.knowledge_texts.extend(cached_data["texts"])
                    print(f"[系统] 加载缓存知识库【{cache_file_path.stem}】，共{len(cached_data['embeddings'])}条向量")
            except Exception as e:
                print(f"[错误] 加载缓存文件[{cache_file_path.name}]失败: {e}")

        # Handle the case where no valid cached data is found
        if not self.knowledge_embeddings:
            print("[系统] 未发现有效知识库缓存，使用空数据填充。")
            # Create a dummy embedding and text to initialize FAISS index if no real data
            dummy_embedding: NDArray[np.float32] = embedding.t2vect(["空数据填充"]).astype(np.float32)
            self.knowledge_embeddings.append(dummy_embedding)
            self.knowledge_texts.append("无有效知识数据")

    def _build_vector_index(self) -> None:
        """Builds the FAISS vector search index from all loaded embeddings."""
        # Concatenate all individual embedding arrays into a single large array
        combined_embeddings: NDArray[np.float32] = np.concatenate(self.knowledge_embeddings)

        # Initialize a FAISS index. IndexFlatIP uses inner product as similarity metric.
        # The dimension of the embeddings is derived from the shape of the combined_embeddings.
        self.faiss_index = faiss.IndexFlatIP(combined_embeddings.shape[1])

        # Add the combined embeddings to the FAISS index
        self.faiss_index.add(combined_embeddings)  # type: ignore
        print(f"[系统] 成功构建FAISS向量索引，总计{self.faiss_index.ntotal}条向量。")

    def retrieve_related_memory(self, query_texts: list[str]) -> str:
        """Retrieves relevant memories based on similarity to the query texts.

        Vectorizes the query texts and performs a similarity search against the
        knowledge base. Filters results based on a predefined similarity threshold.

        Args:
            query_texts: A list of text queries to search for.

        Returns:
            A single string containing all retrieved relevant memory texts,
            separated by double newlines.
        """
        # Vectorize the input query texts
        # Ensure the output is a numpy array of float32 for FAISS compatibility
        query_vectors: NDArray[np.float32] = embedding.t2vect(query_texts).astype(np.float32)

        # Perform a k-nearest neighbor search using the FAISS index
        # D: distances (similarity scores), I: indices of the nearest neighbors
        distances, indices = self.faiss_index.search(query_vectors, self.max_retrieve_count)  # type: ignore

        relevant_memories: list[str] = []
        # Iterate through each query's results
        for query_result_idx in range(len(distances)):  # type: ignore
            # Iterate through the top_k results for the current query
            for neighbor_idx in range(len(distances[query_result_idx])):  # type: ignore
                similarity_score = distances[query_result_idx][neighbor_idx]  # type: ignore
                knowledge_index = indices[query_result_idx][neighbor_idx]  # type: ignore

                # Check if the similarity score meets the threshold and the index is valid
                if similarity_score >= self.similarity_threshold and knowledge_index < len(self.knowledge_texts):
                    memory_text: str = self.knowledge_texts[knowledge_index]  # type: ignore
                    relevant_memories.append(memory_text)  # type: ignore

        # Return unique relevant memories to avoid duplicates if multiple queries return the same text
        # Using a set to ensure uniqueness then converting back to a list
        unique_relevant_memories = list(set(relevant_memories))
        return "\n\n".join(unique_relevant_memories)


# ========= Test Scenario =========


def main() -> None:
    """Main function to test the KnowledgeDataBase class."""
    # Set environment variables to simulate configuration loading
    import os

    # 允许重复的OpenMP运行时库，解决部分环境下的冲突
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    # Mock the settings loading to ensure the test uses specific values
    # In a real application, this would typically load from a file or environment.
    from lab.config_manager import XnneHangLabSettings

    # Create and configure a dummy settings object for the test
    settings_mock = XnneHangLabSettings()  # type: ignore
    settings_mock.agent.memory.books_thresholds = 0.7  # Set a test similarity threshold
    settings_mock.agent.memory.scan_depth = 4  # Set a test maximum retrieval count
    settings_mock.agent.character_name = "test_character"

    # 1. Setup the test environment
    # Define a temporary directory for test knowledge base files
    test_data_base_dir = Path("./chat_history/test_character/data_base")
    # Clean up previous test runs if they exist for a fresh start
    if test_data_base_dir.exists():
        import shutil

        shutil.rmtree(test_data_base_dir.parent)
    test_data_base_dir.mkdir(parents=True, exist_ok=True)

    # 2. Create initial test knowledge base files
    book1_content = {
        "苹果": "苹果是一种水果，有红、绿、黄等颜色",
        "香蕉": "香蕉是热带水果，富含钾元素",
        "橙子": "橙子富含维生素C，果肉多汁",
    }
    book2_content = {
        "汽车": "四轮交通工具，使用汽油或电力驱动",
        "飞机": "航空交通工具，能在高空飞行",
        "自行车": "两轮人力交通工具，环保健康",
    }

    # Write the initial book content to YAML files
    with (test_data_base_dir / "水果知识.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(book1_content, f, allow_unicode=True)

    with (test_data_base_dir / "交通工具.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(book2_content, f, allow_unicode=True)

    print("=" * 50)
    print("测试场景1：初始化数据库并加载知识库")
    print("=" * 50)
    # 3. Initialize the database (this triggers file loading and vectorization)
    db = KnowledgeDataBase(config=settings_mock)

    # Assertions for initial load
    assert isinstance(db, KnowledgeDataBase), "数据库对象类型不正确"
    assert len(db.knowledge_texts) > 0, "知识文本列表不应为空"
    assert db.faiss_index is not None, "FAISS索引未成功初始化"
    assert db.faiss_index.ntotal == len(db.knowledge_texts), "FAISS索引中的向量数量与知识文本数量不匹配"

    # 4. Verify basic loaded data
    print("\n验证加载的知识数量:")
    print(f"知识条目总数: {len(db.knowledge_texts)}")
    print(f"前3条知识: {db.knowledge_texts[:3]}")

    # 5. Perform query tests
    print("\n" + "=" * 50)
    print("测试场景2：相似性检索功能")
    print("=" * 50)

    queries = ["水果", "交通工具", "健康食品"]
    print("\n测试查询:")
    for query in queries:
        results = db.retrieve_related_memory([query])
        print(f"\n查询: '{query}'")
        print(f"结果:\n{results}")
        assert isinstance(results, str), f"查询结果应为字符串, 实际为 {type(results)}"

        if "水果" in query:
            assert "苹果是一种水果" in results or "香蕉是热带水果" in results or "橙子富含维生素C" in results, (
                f"查询'水果'未返回预期结果: {results}"
            )
        elif "交通工具" in query:
            assert "四轮交通工具" in results or "能在高空飞行" in results or "两轮人力交通工具" in results, (
                f"查询'交通工具'未返回预期结果: {results}"
            )

    # 6. Test knowledge base update
    print("\n" + "=" * 50)
    print("测试场景3：知识库更新检测")
    print("=" * 50)

    # Modify an existing file
    book1_content["苹果"] = "苹果是蔷薇科植物果实，品种有富士、嘎啦等，原产于中亚。"
    with (test_data_base_dir / "水果知识.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(book1_content, f, allow_unicode=True)

    # Add a new file
    book3_content = {
        "宇宙飞船": "能在地球大气层外飞行的航天器，用于载人或运载货物。",
        "卫星": "围绕行星轨道运行的人造天体，用于通信或观测。",
    }
    with (test_data_base_dir / "航天器.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(book3_content, f, allow_unicode=True)

    print("\n修改了'水果知识.yaml'并添加了'航天器.yaml'")
    print("重新初始化数据库...")

    db_updated = KnowledgeDataBase(config=settings_mock)

    # Assertions for updated load
    assert len(db_updated.knowledge_texts) > len(db.knowledge_texts), "更新后知识文本数量应增加"
    assert db_updated.faiss_index.ntotal == len(db_updated.knowledge_texts), "更新后FAISS索引向量数量不匹配"

    # 7. Verify updated queries
    print("\n更新后查询'苹果':")
    results_apple_updated = db_updated.retrieve_related_memory(["苹果"])
    print(results_apple_updated)
    assert "蔷薇科植物果实" in results_apple_updated, "更新后查询'苹果'未返回新内容"

    print("\n查询'航天器':")
    results_spacecraft = db_updated.retrieve_related_memory(["航天器"])
    print(results_spacecraft)
    assert "地球大气层外飞行的航天器" in results_spacecraft or "围绕行星轨道运行的人造天体" in results_spacecraft, (
        "查询'航天器' 未返回相关内容"
    )

    print("\n" + "=" * 50)
    print("测试完成。")
    print("=" * 50)


if __name__ == "__main__":
    main()
