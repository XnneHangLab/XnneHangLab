from __future__ import annotations

import asyncio

# from typing import Any
import json
from abc import ABC, abstractmethod
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult
from openai import AsyncOpenAI
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.mcp._typing import CommonMessage, ToolMessage
from lab.mcp.openai_client import read_prompt_from_mcp_prompt_template, read_result_from_mcp_tool_response


class MCPHandlerInterface(ABC):
    def __init__(self, mcp_client: ClientSession):
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)
        self.mcp_client = mcp_client
        self.openai_client = AsyncOpenAI(
            base_url=self.config.agent.llm.gemini.llm_base_url, api_key=self.config.agent.llm.gemini.llm_api_key
        )
        self.tool_responses: list[ToolMessage] = []
        self.messages: list[dict[str, object] | ToolMessage | CommonMessage] = []

    @classmethod
    async def create(cls, mcp_client: ClientSession):
        instance = cls(mcp_client)
        await instance._async_init()
        return instance

    async def add_messages(self, message: ToolMessage | CommonMessage):
        self.messages.append(message)  # 从 basic memory 处得到记忆更新，防止回复断层丢失上下文。

    async def _async_init(self):
        self.tool_list = await self.mcp_client.list_tools()
        # 转换为OpenAI格式的工具描述
        self.available_tools = [
            {
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": tool.inputSchema},
            }
            for tool in self.tool_list.tools
        ]

    @abstractmethod
    async def process(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """处理消息,并且筛查是否需要调用工具。"""
        raise ValueError("No MCP server pass in")

    @abstractmethod
    async def generate_prompt_template(self, tool_name: str, tool_response: CallToolResult) -> str:
        """为 tool 选择、组合生成Prompt模板"""
        raise ValueError("No MCP server pass in")


class ExampleMCPHandler(MCPHandlerInterface):
    # 为我们的 example server 生成的 MCPHandler, 对于不同功能，可以生成不同 server, 每个 server 使用不同 handler 进行隔离。
    # 对于多个 mcp server ，在这一步要先合并 available_tools:
    """response = await client.chat.completions.create(  # type: ignore[return-value]
        model=self.config.agent.llm.gemini.llm_model_name,
        messages=messages,  # type: ignore[assignment]
        tools=available_tools,  # type: ignore[assignment]
        tool_choice="auto",  # 让模型自行决定是否调用工具
    )
    """

    # 然后最后再对 tool_name 做遍历选择合适的 handler

    async def generate_prompt_template(self, tool_name: str, tool_response: CallToolResult) -> str:
        prompt = ""
        if tool_name == "get_date_and_time":
            prompt_response = await self.mcp_client.get_prompt(
                "convert_time_readable", {"time_str": read_result_from_mcp_tool_response(tool_response)}
            )
            prompt = read_prompt_from_mcp_prompt_template(prompt_response)
        if tool_name == "roll_dice":
            prompt_response = await self.mcp_client.get_prompt(
                "convert_list_int_readable", {"numbers": read_result_from_mcp_tool_response(tool_response)}
            )
            prompt = read_prompt_from_mcp_prompt_template(prompt_response)
        return prompt

    async def process(self, response_message: ChatCompletionMessage):  # type: ignore[override]
        if not response_message.tool_calls:
            # 并不是工具调用，直接退出即可.
            print("No tool call")
            if response_message.content:
                self.messages.append(CommonMessage(role="assistant",content=response_message.content)) # user 的只能从外部 append
                return CommonMessage(role="assistant",content=response_message.content)
            else:
                return CommonMessage(role="assistant",content="No response content in no tool call")


        else:
            print("tool call")
            # 生成Prompt模板并且加入 messages
            tool_name = response_message.tool_calls[
                0
            ].function.name  # TODO 也许能实现多个 tool 的功能？但是可能过于复杂暂时不考虑
            tool_args = json.loads(response_message.tool_calls[0].function.arguments)
            tool_response = await self.mcp_client.call_tool(tool_name, tool_args)
            prompt = await self.generate_prompt_template(response_message.tool_calls[0].function.name, tool_response)
            # 加入 prompt
            if prompt != "":
                self.messages.append(
                    CommonMessage(role="user", content=prompt)
                )  # 研究一下后续怎么退火 =-=, 把这个提示词给删掉。 or, 这个提示词仅存在于我们 MCPHandler 的 messages 中不存在于 BasicMemoryAgent 的 messages 中，这很合理。
            # 加入初次生成的 response
            self.messages.append(response_message.to_dict())
            # 加入调用工具生成的 response
            self.messages.append(
                ToolMessage(
                    role="tool",
                    content=read_result_from_mcp_tool_response(tool_response),
                    tool_call_id=response_message.tool_calls[0].id,
                )
            )
            final_response = await self.openai_client.chat.completions.create(
                model=self.config.agent.llm.gemini.llm_model_name,
                messages=self.messages,  # type: ignore[assignment]
            )
            if final_response.choices[0].message.content:
                self.messages.append(CommonMessage(role="assistant", content=final_response.choices[0].message.content))
                return CommonMessage(role="assistant", content=final_response.choices[0].message.content)
            else:
                return CommonMessage(role="assistant", content="second call tool return None")


class MCPConnection:
    def __init__(self, server_path: str):
        self.exit_stack = AsyncExitStack()
        self.session = None
        self.server_path = server_path

    async def __aenter__(self):
        server_params = StdioServerParameters(command="uv", args=["run", self.server_path], env=None)
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
        await self.session.initialize()
        return self.session

    async def __aexit__(self, *exc_info):  # type: ignore
        await self.exit_stack.aclose()


async def main():
    async with MCPConnection("src/lab/mcp/server.py") as session:
        mcp_handler = await ExampleMCPHandler.create(session)
        openai_client = mcp_handler.openai_client
        message = CommonMessage(role="user",content="你好，现在几点？")
        await mcp_handler.add_messages(message)
        response = await openai_client.chat.completions.create(  # type: ignore[return-value]
            model=mcp_handler.config.agent.llm.gemini.llm_model_name,
            messages=mcp_handler.messages,  # type: ignore[assignment]
            tools=mcp_handler.available_tools,  # type: ignore[assignment]
            tool_choice="auto",  # 让模型自行决定是否调用工具
        )
        await mcp_handler.process(response_message = response.choices[0].message)
        print(mcp_handler.messages)



if __name__ == "__main__":
    asyncio.run(main())
