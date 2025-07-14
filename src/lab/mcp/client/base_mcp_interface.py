from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

# from mcp import ClientSession, StdioServerParameters
# from mcp.client.stdio import stdio_client
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from loguru import logger
from openai import AsyncOpenAI

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.mcp._typing import CommonMessage, ImageMessage, ToolMessage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.types import CallToolResult
    from openai.types.chat.chat_completion_message import ChatCompletionMessage


class MCPHandlerInterface(ABC):
    def __init__(self):
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)
        self.openai_client = self.init_openai_client()
        self.messages: list[dict[str, object] | ToolMessage | CommonMessage | ImageMessage] = self.reset_messages()
        self.available_tools: list[dict[str, object]] = []
        # Basic connection
        # self.transport = StreamableHttpTransport(url="https://api.example.com/mcp")
        # self.mcp_client = Client(self.transport)
        self.transport: StreamableHttpTransport = None  # type: ignore
        self.mcp_client: Client = None  # type: ignore
        # With custom headers for authentication
        # transport = StreamableHttpTransport(
        #     url="https://api.example.com/mcp",
        #     headers={
        #         "Authorization": "Bearer your-token-here",
        #         "X-Custom-Header": "value"
        #     }
        # )

    @classmethod
    async def create(cls, server_url: str):
        instance = cls()
        if instance.config.agent.llm_provider == "lingyi":
            logger.warning("Lingyi LLM is not supported in MCP Tool Call")
            return None
        await instance._async_init(server_url)
        return instance

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

        return self.openai_client

    def get_openai_model_name(self):
        if self.config.agent.llm_provider == "gemini":
            return self.config.agent.llm.gemini.llm_model_name
        elif self.config.agent.llm_provider == "lingyi":
            return self.config.agent.llm.lingyi.llm_model_name
        elif self.config.agent.llm_provider == "openai":
            return self.config.agent.llm.openai.llm_model_name
        else:
            raise ValueError("Unknown llm provider")

    async def _async_init(self, server_url: str):
        self.transport = StreamableHttpTransport(url=server_url)
        self.mcp_client = Client(self.transport)
        async with self.mcp_client:  # type: ignore
            tool_list = await self.mcp_client.list_tools()  # type: ignore
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
    ) -> list[
        CommonMessage | ToolMessage | dict[str, object] | ImageMessage
    ]:  # 创建一个无上下文的 mcp handler 判断要不要调用工具.
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
