# 角色模板
from __future__ import annotations

import ast

# import yaml
import asyncio
import json

# from ruamel.yaml import YAML
# from ruamel.yaml.scalarstring import PreservedScalarString
import time
from pathlib import Path

import jionlp
from openai import AsyncOpenAI

from lab.agent.memory.core_mem import CoreMemory
from lab.agent.memory.knowlege_base import KnowledgeDataBase
from lab.agent.memory.long_memory import LongTermMemory
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.mcp import CommonMessage
from lab.utils.TxtHelper import read_tool_prompt_from_text_file


class MemoryManager:
    def update_config(self):
        # 载入配置
        self.char = self.config.agent.character_name
        self.user = "xnne"

        # self.data_base_thresholds = self.config.agent.memory.books_thresholds
        # self.data_base_depth = self.config.agent.memory.scan_depth
        # self.enable_long_mem = self.config.agent.memory.en
        # self.is_check_memorys = self.config.agent.memory.enable_check_memorys
        # self.mem_thresholds = self.config.agent.memory.mem_thresholds

        # self.llm_config = CConfig.config["LLM"]

        # 载入提示词
        # self.long_mem_prompt = read_tool_prompt_from_text_file("long_term_memory_reader")
        # self.data_base_prompt = read_tool_prompt_from_text_file("knowledge_base_reader")
        # self.core_mem_prompt = read_tool_prompt_from_text_file("core_memory_reader")
        self.last_core_mem_insert_index = 0

    def init_openai_client(self):
        if self.config.agent.llm_provider == "gemini":
            self.openai_client = AsyncOpenAI(
                base_url=self.config.agent.llm.gemini.llm_base_url,
                api_key=self.config.agent.llm.gemini.llm_api_key,
            )
        elif self.config.agent.llm_provider == "lingyi":
            self.openai_client = AsyncOpenAI(
                base_url=self.config.agent.llm.lingyi.llm_base_url,
                api_key=self.config.agent.llm.lingyi.llm_api_key,
            )
        elif self.config.agent.llm_provider == "openai":
            self.openai_client = AsyncOpenAI(
                base_url=self.config.agent.llm.openai.llm_base_url,
                api_key=self.config.agent.llm.openai.llm_api_key,
            )
        else:
            raise ValueError("Unknown llm provider")

    def get_openai_model_name(self):
        if self.config.agent.llm_provider == "gemini":
            return self.config.agent.llm.gemini.llm_model_name
        elif self.config.agent.llm_provider == "lingyi":
            return self.config.agent.llm.lingyi.llm_model_name
        elif self.config.agent.llm_provider == "openai":
            return self.config.agent.llm.openai.llm_model_name
        else:
            raise ValueError("Unknown llm provider")

    def __init__(self, config: XnneHangLabSettings | None = None):
        self.config = config if config else load_settings_file("lab.toml", XnneHangLabSettings)
        self.update_config()
        # 這個 message data 是獨立的，通過手動同步，以及它是最終發送給 llm 的， 因為會帶有很多其他的信息，比如核心记忆，知识库，長期记忆，所以不能直接使用 msg_data_tmp
        # 我們隔離了 Tool Message, 通過 MCP_Client 裡的 msg_data。
        # 我們隔離了 知识库等内容，通过这个。
        self.msg_data_tmp: list[CommonMessage] = []
        # 创建系统时间戳
        self.tt = int(time.time())

        # 创建数据存储文件夹
        Path(f"./chat_history/{self.char}/memorys").mkdir(parents=True, exist_ok=True)
        Path(f"./chat_history/{self.char}/data_base").mkdir(parents=True, exist_ok=True)

        # 加载角色记忆
        self.memorys = LongTermMemory(self.config)
        # 加载核心记忆
        self.core_mem = CoreMemory(self.config)
        # 载入知识库
        self.knowledge_base = KnowledgeDataBase(self.config)
        self.init_openai_client()

    # 知识库内容检索
    def get_related_data_from_kownledge_base(self, user_input: str) -> str | None:
        split_sentences: list[str] = jionlp.split_sentence(user_input, criterion="fine")  # type: ignore
        res_ = self.knowledge_base.retrieve_related_memory(split_sentences)
        if res_ != "":
            return res_
        else:
            return None

    # 提取、插入核心记忆
    async def insert_core_mem(
        self, messages: list[CommonMessage]
    ):  # 因为不是所有的模型都支持 mcp tool call, 所以这里加上一个手动调用。 mcp 只用于增强。
        """
        将最近的三条消息作为上下文用以提取核心记忆。
        msg: 外部实际存储的 Agent 实际存储的 Message, 不带有 Tool Message, 不带有知识库， 日记，和引导。
        """
        core_memory_extract_prompt = read_tool_prompt_from_text_file("core_memory_writer").replace(
            "{{memories}}", json.dumps(self.core_mem.raw_memory_texts[-100:], ensure_ascii=False)
        )  # 这个 prompt 似乎不是这俩
        if len(messages) <= 3:
            return  # 不足三条，不提取, 因为会有一条系统，不希望系统加入
        if len(messages) - self.last_core_mem_insert_index <= 3:
            return  # 距离上次插入过短，不提取
        if (
            messages[-1]["role"] != "assistant"
            and messages[-2]["role"] != "user"
            and messages[-3]["role"] != "assistant"
        ):
            return  # 符合 助手-用户-助手 的格式
        contant = (
            "对话内容：助手："
            + messages[-3]["content"]
            + "\n用户："
            + messages[-2]["content"]
            + "\n助手："
            + messages[-1]["content"]
        )
        data = [
            CommonMessage(role="system", content=core_memory_extract_prompt),
            CommonMessage(role="user", content=contant),
        ]
        try:
            # 使用异步 OpenAI 客户端调用
            res_msg = await self.openai_client.chat.completions.create(
                model=self.get_openai_model_name(),
                messages=data,  # type: ignore[assignment]
            )
            response_message = res_msg.choices[0].message
            if response_message:
                mem_list_str = jionlp.extract_parentheses(response_message, "[]")[0].replace(" ", "").replace("\n", "")  # type: ignore
                mem_list = ast.literal_eval(mem_list_str)  # type: ignore
                if len(mem_list) > 0:
                    self.core_mem.add_memory(mem_list)
                    self.last_core_mem_insert_index = len(messages)  # 更新插入索引
            else:
                print("Failed to get core memory extraction from LLM.")

        except Exception as e:
            print(f"Error during core memory extraction: {e}")
            # 这里可以根据需要添加更详细的错误日志或处理
            return

    # 将用户最后一条消息加工为带引导的上下文。
    async def process_user_message(self, user_message: str) -> str:
        """
        处理用户的最新消息，通过并行检索知识库、长期记忆和核心记忆来生成引导式上下文。

        Args:
            user_message: 用户的最后一条消息内容。

        Returns:
            CommonMessage 对象的列表，表示包含引导、检索信息和用户消息的完整上下文。
        """
        # 初始化上下文消息列表，从预设的 prompt 开始
        current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")  # 获取当前时间

        # 使用 asyncio.gather 并行运行所有耗时任务
        # 注意：这里假设 self.memorys.get_memorys 和 self.core_mem.find_mem 也是同步方法
        # 且它们接受的参数和返回值需要与实际匹配。
        # 原代码中的 mem_msg 和 core_mem 是作为参数传入的列表，
        # 这种模式在 asyncio.to_thread 中不直接适用（因为异步结果是直接返回的）。
        # 这里我修改为直接接收返回值。

        # 为 get_memorys 和 find_mem 模拟返回一个字符串，以便和 data_base 的处理逻辑匹配
        # 你需要根据这些方法的实际返回值来调整这里。
        async def get_memories_wrapper(query: str):
            # 假设 Memorys.get_memorys(msg) 返回的是一个字符串或 None
            # 如果它需要修改传入的列表，则需要更复杂的同步机制，但这通常不是推荐的异步模式。
            res = await asyncio.to_thread(self.memorys.get_memorys, query, [], current_time_str)
            return res if res else None  # 确保返回 None 或实际内容

        async def find_core_mem_wrapper(query: str):
            # 假设 Core_mem.find_mem(msg) 返回的是一个字符串或 None
            res = await asyncio.to_thread(self.core_mem.find_memory, query)
            return res if res else None  # 确保返回 None 或实际内容

        # 创建并等待所有并行任务
        knowledge_base_task = asyncio.create_task(
            asyncio.to_thread(self.get_related_data_from_kownledge_base, user_message)
        )
        long_memory_task = asyncio.create_task(
            get_memories_wrapper(user_message)
            # await asyncio.to_thread(self.memorys.get_memorys, user_message) # 假设get_memorys返回一个字符串
        )
        core_memory_task = asyncio.create_task(
            find_core_mem_wrapper(user_message)
            # await asyncio.to_thread(self.core_mem.find_mem, user_message) # 假设find_mem返回一个字符串
        )

        # 等待所有任务完成并获取结果
        kb_result, mem_result, core_mem_result = await asyncio.gather(
            knowledge_base_task, long_memory_task, core_memory_task
        )
        user_prompt_template = f"""
        [辅助参考资料]
        ---
        世界书: [world_book_section]
        你与用户的核心记忆: [core_memory_section]
        长期记忆: [long_term_memory_section]
        当前现实世界时间：{current_time_str}；一定要基于现实世界时间做出适宜的回复。
        ---
        请结合我给你提供的参考资料如果它们不为空然后回答用户的当前对话请求，但不要过于机械。
        ---
        [当前对话请求]
        [user_query]
        """
        # 合并检索到的信息到 context_messages
        if kb_result:
            user_prompt_template = user_prompt_template.replace("[world_book_section]", kb_result)
        if core_mem_result:
            user_prompt_template = user_prompt_template.replace("[core_memory_section]", str(core_mem_result))
        if mem_result:
            user_prompt_template = user_prompt_template.replace("[long_term_memory_section]", str(mem_result))
        user_prompt_template = user_prompt_template.replace("[user_query]", user_message)
        return user_prompt_template
