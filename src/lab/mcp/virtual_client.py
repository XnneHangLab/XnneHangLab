from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.mcp._typing import CommonMessage, ToolMessage
from lab.mcp.client.base_mcp_interface import MCPHandlerInterface
from lab.mcp.client.timeemi import TimeemiMCPHandler
from lab.mcp.connect import MCPConnection
from lab.mcp.util import read_prompt_from_text_file

if TYPE_CHECKING:
    from mcp.types import CallToolResult


class VirtualMCPHandler(MCPHandlerInterface):
    # 本身不带有任何 method, 只是用于整合各个 MCPHandler 的 available tools 然后判断是否需要 tool call, 具体不同功能，位于 server, 每个 server 使用不同 handler 进行隔离。
    # 然后最后再对 tool_name 做遍历选择合适的 handler
    def __init__(self, handlers: list[MCPHandlerInterface]):
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)
        # self.mcp_client = mcp_client 本身是不具有 mcp_client 的
        self.openai_client = AsyncOpenAI(
            base_url=self.config.agent.llm.gemini.llm_base_url, api_key=self.config.agent.llm.gemini.llm_api_key
        )
        self.messages: list[dict[str, object] | ToolMessage | CommonMessage] = self.reset_messages()
        self.handlers: list[MCPHandlerInterface] = handlers
        if len(self.handlers) == 0:
            raise ValueError("未初始化任何 MCPHandler")
        self.available_tools = []
        for handler in self.handlers:
            self.available_tools.extend(handler.available_tools)

    async def generate_prompt_template(
        self, tool_name: str, tool_response: CallToolResult, user_input: str
    ) -> list[CommonMessage]:
        return []

    def find_handler_by_tool(self, tool_name: str, handlers: list[MCPHandlerInterface]) -> MCPHandlerInterface:
        """通过工具名称查找对应的 handler"""
        for handler in self.handlers:
            for tool in handler.available_tools:
                if tool["function"]["name"] == tool_name:  # type: ignore
                    return handler
        raise ValueError(f"未找到工具 {tool_name} 对应的 handler")

    async def process(self, message: CommonMessage, memory: list[CommonMessage]):  # type: ignore[override]
        self.messages = self.reset_messages()
        self.messages.append(message)
        # print(self.messages)
        response = await self.openai_client.chat.completions.create(  # type: ignore[return-value]
            model=self.config.agent.llm.gemini.llm_model_name,
            messages=self.messages,  # type: ignore[assignment]
            tools=self.available_tools,  # type: ignore[assignment]
            tool_choice="auto",  # 让模型自行决定是否调用工具
        )
        response_message = response.choices[0].message

        if not response_message.tool_calls:  # 对于 tool call stream response 的屈服。宁可多调用一次也不能放弃 stream。
            self.messages = deepcopy(
                memory
            )  # 防止 memory 被篡改,我们不希望在 memory 中加入 tool 上下文。 # type:ignore
            self.messages.append(message)
            stream = await self.openai_client.chat.completions.create(  # type: ignore[return-value]
                model=self.config.agent.llm.gemini.llm_model_name,
                messages=self.messages,  # type: ignore[assignment]
                stream=True,
            )
            async for chunk in stream:  # type: ignore[assignment]
                if chunk.choices[0].delta.content is None:  # type: ignore[assignment]
                    chunk.choices[0].delta.content = ""  # type: ignore[assignment]
                yield chunk.choices[0].delta.content  # type: ignore[assignment]
        else:
            self.messages = deepcopy(
                memory
            )  # 防止 memory 被篡改,我们不希望在 memory 中加入 tool 上下文。 # type:ignore
            self.messages.append(message)
            tool_name = response_message.tool_calls[
                0
            ].function.name  # TODO 也许能实现多个 tool 的功能？但是可能过于复杂暂时不考虑
            # tool_args = json.loads(response_message.tool_calls[0].function.arguments)
            handler = self.find_handler_by_tool(tool_name, self.handlers)
            async for chunk in handler.process(response_message=response_message, memory=memory, message=message):  # type:ignore
                yield chunk


# example usage:
async def main():
    async with MCPConnection("src/lab/mcp/server/timeemi.py") as timeemi_session:
        timeemi_mcp_handler = await TimeemiMCPHandler.create(timeemi_session)
        virtual_mcp_handler = VirtualMCPHandler(handlers=[timeemi_mcp_handler])
        virtual_mcp_handler.available_tools.extend(timeemi_mcp_handler.available_tools)
        memory = [CommonMessage(role="system", content=read_prompt_from_text_file("elaina"))]
        message = CommonMessage(role="user", content="你今天真可爱")
        print(f"user input: {message}")
        async for chunk in virtual_mcp_handler.process(message=message, memory=memory):  # type: ignore
            print(chunk)  # type: ignore
        print(virtual_mcp_handler.messages)
        message = CommonMessage(role="user", content="现在几点了？")
        print(f"user input: {message}")
        async for chunk in virtual_mcp_handler.process(message=message, memory=memory):  # type: ignore
            print(chunk)  # type: ignore
        print(virtual_mcp_handler.messages)


if __name__ == "__main__":
    asyncio.run(main())
