from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from anyio import Path
from fastmcp import Client
from openai import AsyncOpenAI

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.mcp._typing import CommonMessage, ToolMessage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.types import CallToolResult
    from openai.types.chat.chat_completion_message import ChatCompletionMessage


class MCPHandlerInterface(ABC):
    def __init__(self):
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)
        self.openai_client = AsyncOpenAI(
            base_url=self.config.agent.llm.gemini.llm_base_url,
            api_key=self.config.agent.llm.gemini.llm_api_key,
        )
        self.messages: list[dict[str, object] | ToolMessage | CommonMessage] = self.reset_messages()
        self.available_tools: list[dict[str, object]] = []
        self.mcp_client: Client | None = None  # type: ignore

    @classmethod
    async def create(cls, server_path: str):
        instance = cls()
        await instance._async_init(server_path)
        return instance

    async def _async_init(self, server_path: str):
        if not await Path(server_path).exists():
            raise ValueError(f"Server path {server_path} does not exist")
        self.mcp_client = Client(server_path)
        async with self.mcp_client as client:  # type: ignore
            tool_list = await client.list_tools()
            # print(tool_list)
        self.available_tools = [
            {
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": tool.inputSchema},
            }
            for tool in tool_list
        ]

    @abstractmethod
    async def process(
        self, response_message: ChatCompletionMessage, memory: list[CommonMessage], message: CommonMessage
    ) -> AsyncIterator[CommonMessage]:
        """处理消息并返回流式响应"""
        raise NotImplementedError

    @abstractmethod
    async def generate_prompt_template(
        self, tool_name: str, tool_response: CallToolResult, user_input: str
    ) -> list[CommonMessage]:
        """为 tool 选择、组合生成Prompt模板"""
        raise NotImplementedError

    def add_messages(self, message: ToolMessage | CommonMessage):
        self.messages.append(message)  # 从 basic memory 处得到记忆更新，防止回复断层丢失上下文。

    def reset_messages(
        self,
    ) -> list[CommonMessage | ToolMessage | dict[str, object]]:  # 创建一个无上下文的 mcp handler 判断要不要调用工具.
        messages = [
            CommonMessage(
                role="system",
                content="你是一个做事干净利落的助手，总能够快速地响应问题和需求，并且用最简洁的话回答问题。",
            )
        ]
        if self.config.agent.user_lang == "ZH":
            messages.append(CommonMessage(role="system", content="你使用中文回答问题"))
        elif self.config.agent.user_lang == "EN":
            messages.append(CommonMessage(role="system", content="你使用英文回答问题"))
        elif self.config.agent.user_lang == "JA":
            messages.append(CommonMessage(role="system", content="你使用日文回答问题"))
        else:
            raise ValueError("Unknown user lang")
        return messages  # type: ignore[return-value]
