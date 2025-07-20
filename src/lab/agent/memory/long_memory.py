from __future__ import annotations

import pickle
import time
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import Annotated, Any

import jionlp as jio
import numpy as np
import requests
import yaml
from numpy.typing import NDArray
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from lab.agent.memory import embedding
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.utils.TxtHelper import read_prompt_from_text_file


class LongTermMemory:
    """长期记忆管理系统，负责记忆的存储、检索和持久化"""

    def __init__(self):
        # 加载配置文件
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)
        self._init_memory_attributes()

        # 记忆存储路径（使用pathlib处理路径）
        self.memory_dir = Path(f"./chat_history/{self.char_name}/memorys")
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 初始化记忆存储结构
        self.timestamp_keys: list[int] = []  # 按时间排序的时间戳（秒级）
        self.memory_records: dict[int, str] = {}  # {时间戳: 记忆文本}
        self.tag_vectors: NDArray[np.float32] = np.array([])  # 记忆标签的向量数组

        self._load_existing_memories()

    def _init_memory_attributes(self):
        """从配置初始化记忆相关属性"""
        self.char_name = self.config.agent.system_prompt_name  # 角色名称
        self.user_name = "xnnehang"  # 固定用户名
        self.similarity_threshold = self.config.agent.memory.mem_thresholds  # 相似度阈值
        self.enable_semantic_check = self.config.agent.memory.enable_check_memorys  # 是否启用语义检查

    def _load_existing_memories(self):
        """加载已存在的记忆数据和向量"""
        vector_cache: list[NDArray[np.float32]] = []

        # 遍历记忆存储目录（使用pathlib的glob模式）
        for mem_file in self.memory_dir.glob("*.yaml"):
            try:
                # 加载YAML格式的记忆文件
                with mem_file.open("r", encoding="utf-8") as f:
                    records: dict[str, Any] = yaml.safe_load(f) or {}
                    self._process_memory_records(records)

                # 尝试加载预计算的向量缓存
                vec_file = mem_file.with_suffix(".pkl")
                if vec_file.exists():
                    with vec_file.open("rb") as f:
                        cached_vectors = pickle.load(f)
                        self.tag_vectors = np.concatenate([self.tag_vectors, cached_vectors])
                    print(f"[成功] 加载记忆向量缓存：{mem_file.name}")
                else:
                    print(f"[处理中] 正在生成记忆向量：{mem_file.name}")
                    new_vectors = embedding.t2vect(list(self.memory_records.values()))
                    vector_cache.extend(new_vectors)
                    self._save_vector_cache(vec_file, new_vectors)

            except Exception as e:
                print(f"[错误] 加载记忆文件失败：{mem_file}\n{str(e)}")
                continue

        print(f"[完成] 共加载 {len(self.timestamp_keys)} 条记忆，{len(self.tag_vectors)} 个向量")

    def _process_memory_records(self, records: dict[str, Any]):
        """处理单个记忆文件中的记录"""
        for ts, data in records.items():
            processed_text = str(data["msg"]).replace("{{user}}", self.user_name).replace("{{char}}", self.char_name)
            self.memory_records[ts] = processed_text  # type: ignore
            self.timestamp_keys.append(ts)  # type: ignore

    def _save_vector_cache(self, file_path: Path, vectors: list[NDArray[np.float32]]):
        """保存生成的向量到缓存文件"""
        with file_path.open("wb") as f:
            pickle.dump(vectors, f)
        print(f"[完成] 已缓存向量文件：{file_path.name}")

    def find_time_range(self, start_ts: int, end_ts: int) -> tuple[int, int] | None:
        """使用二分查找定位时间范围内的记忆索引"""
        left = bisect_left(self.timestamp_keys, start_ts)
        right = bisect_right(self.timestamp_keys, end_ts)
        return (left, right - 1) if right > left else None

    def get_memorys(self, msg: str, result_list: list[str], time_node: str) -> list[str]:
        """获取与文本相关的记忆"""
        if not self.timestamp_keys:
            return []

        time_spans = self._extract_time_spans(msg, time_node)
        if not time_spans:
            return []

        start_idx, end_idx = time_spans
        if self.enable_semantic_check:  # 基于语义搜？
            return self._semantic_search(msg, start_idx, end_idx, result_list)
        return self._direct_search(start_idx, end_idx, result_list)

    def _extract_time_spans(self, msg: str, time_node: str) -> tuple[int, int] | None:
        """提取文本中的时间范围"""  # 似乎是不依赖大模型的,这个可以用 mcp 改善，只不过时间复杂度上就会变高，而且导致 long_term_memory 和 mcp 就必须得耦合，分开设计也挺好的
        time_entities = jio.ner.extract_time(f"[{time_node}]{msg}", time_base=time.time(), with_parsing=False)  # type: ignore

        time_spans = []
        for entity in time_entities[1:]:  # type: ignore
            try:
                parsed_time = jio.parse_time(entity["text"], time_base=time_entities[0]["text"])  # type: ignore
                start = int(time.mktime(time.strptime(parsed_time["time"][0], "%Y-%m-%d %H:%M:%S")))  # type: ignore
                end = int(time.mktime(time.strptime(parsed_time["time"][1], "%Y-%m-%d %H:%M:%S")))  # type: ignore
                time_spans.extend([start, end])  # type: ignore
            except Exception as e:
                print(f"[错误] 时间解析失败：{str(e)}")

        return self.find_time_range(time_spans[0], time_spans[1]) if time_spans else None  # type: ignore

    def _semantic_search(
        self, msg: str, start: int, end: int, result: list[str]
    ) -> list[
        str
    ]:  # for a while, 虽然 result 是一个指针可以直接修改其内容，但是最好还是返回一下比较好,它有助于理解输入输出和意图
        """基于语义相似度的记忆检索"""
        print(f"[提示] 深度检索记忆，阈值：{self.similarity_threshold}")
        query_vector = embedding.t2vect([msg])[0]
        relevant_memories: list[str] = []

        for idx in range(start + 1, end + 1):
            similarity = np.dot(self.tag_vectors[idx], query_vector)  # TODO 相当困惑的地方
            if similarity >= self.similarity_threshold:
                relevant_memories.append(str(self.memory_records[self.timestamp_keys[idx]]))

        if relevant_memories:
            result.append("\n".join(relevant_memories))

        return result

    def _direct_search(self, start: int, end: int, result: list[str]) -> list[str]:
        """直接时间范围记忆检索"""
        memories = [str(self.memory_records[self.timestamp_keys[idx]]) for idx in range(start + 1, end + 1)]
        if memories:
            result.append("\n".join(memories))
        return result

    def add_memory(self, memory_data: dict[str, Any]) -> None:
        """写入新记忆"""
        timestamp = int(memory_data["t_n"])
        self.timestamp_keys.append(timestamp)
        self.memory_records[timestamp] = memory_data["msg"]

        # 生成并保存向量
        tag_vector = embedding.t2vect([memory_data["text_tag"]])[0]
        self.tag_vectors = np.append(self.tag_vectors, [tag_vector], axis=0)

        # 构建存储路径
        time_struct = time.localtime(timestamp)
        date_str = f"{time_struct.tm_year}-{time_struct.tm_mon}-{time_struct.tm_mday}"
        yaml_file = self.memory_dir / f"{date_str}.yaml"
        pkl_file = self.memory_dir / f"{date_str}.pkl"

        # 使用ruamel.yaml保持格式
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.width = 4096

        # 追加写入YAML文件
        with yaml_file.open("a", encoding="utf-8") as f:
            yaml.dump(
                {timestamp: {"text_tag": memory_data["text_tag"], "msg": LiteralScalarString(memory_data["msg"])}}, f
            )

        # 更新向量缓存
        day_start = timestamp - (timestamp - time.timezone) % 86400
        cache_idx = bisect_left(self.timestamp_keys, day_start)
        with pkl_file.open("wb") as f:
            pickle.dump(self.tag_vectors[cache_idx:], f)

    # 提取记忆摘要，记录长期记忆
    def add_memory1(self, data: list[dict[str, str]], t_n: int, llm_config: dict[str, str]):
        mmsg = read_prompt_from_text_file("memory_assistant")
        res_msg = "用户：" + data[-2]["content"]
        res_body = {
            "model": llm_config["model"],
            "messages": [{"role": "system", "content": mmsg}, {"role": "user", "content": res_msg}],
        }
        key = llm_config["key"]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        res_tag = ""
        try:
            res = requests.post(llm_config["api"], json=res_body, headers=headers, timeout=15)
            res = res.json()["choices"][0]["message"]["content"]
            res = jio.remove_html_tag(res).replace(" ", "").replace("\n", "")  # type: ignore
            print(f"[记录日记结果]【{res}】")
            if res.find("日常闲聊") == -1:
                res_tag = res
            else:
                res_tag = "日常闲聊"
        except Exception as e:
            print("【错误获取聊天信息失败！】")
            res_tag = "日常闲聊"
        t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t_n))
        m1 = data[-2]["content"]
        m2 = data[-1]["content"]
        c1 = "{{user}}"
        c2 = "{{char}}"
        m_data = {"t_n": t_n, "text_tag": res_tag, "msg": f"时间：{t_str}\n{c1}：{m1}\n{c2}：{m2}"}
        self.add_memory(m_data)
