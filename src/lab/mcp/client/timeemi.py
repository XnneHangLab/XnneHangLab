from __future__ import annotations

# from typing import Any
import json
from copy import deepcopy
from typing import TYPE_CHECKING

from lab.mcp._typing import CommonMessage, ToolMessage
from lab.mcp.client.base_mcp_interface import MCPHandlerInterface
from lab.mcp.example.openai_client import (
    read_prompt_from_mcp_prompt_template,
    read_result_from_mcp_tool_response,
)

if TYPE_CHECKING:
    from mcp.types import CallToolResult
    from openai.types.chat.chat_completion_message import ChatCompletionMessage


class TimeemiMCPHandler(MCPHandlerInterface):
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

    async def generate_prompt_template(
        self, tool_name: str, tool_response: CallToolResult, user_input: str
    ) -> list[CommonMessage]:
        if self.mcp_client is None:  # type: ignore
            raise ValueError("mcp client is None")
        messages: list[CommonMessage] = []
        async with self.mcp_client:  # type: ignore
            if tool_name == "get_date_and_time":
                prompt_response = await self.mcp_client.get_prompt(  # type: ignore
                    "convert_time_readable", {"time_str": read_result_from_mcp_tool_response(tool_response)}
                )
                messages.append(
                    CommonMessage(role="user", content=read_prompt_from_mcp_prompt_template(prompt_response))
                )
                prompt_response = await self.mcp_client.get_prompt("limit_time_response", {"user_input": user_input})  # type: ignore
                messages.append(
                    CommonMessage(role="user", content=read_prompt_from_mcp_prompt_template(prompt_response))
                )

            if tool_name == "roll_dice":
                prompt_response = await self.mcp_client.get_prompt(  # type: ignore
                    "convert_list_int_readable", {"numbers": read_result_from_mcp_tool_response(tool_response)}
                )
                messages.append(
                    CommonMessage(role="user", content=read_prompt_from_mcp_prompt_template(prompt_response))
                )
        return messages

    async def process(  # type: ignore[override]
        self, response_message: ChatCompletionMessage, memory: list[CommonMessage], message: CommonMessage
    ):  # type: ignore[override]
        # 生成Prompt模板并且加入 messages
        if not response_message.tool_calls:
            raise ValueError("No tool call in response")
        if self.mcp_client is None:  # type: ignore
            raise ValueError("mcp client is None")
        tool_name = response_message.tool_calls[
            0
        ].function.name  # TODO 也许能实现多个 tool 的功能？但是可能过于复杂暂时不考虑
        tool_args = json.loads(response_message.tool_calls[0].function.arguments)
        async with self.mcp_client:  # type: ignore
            tool_response = await self.mcp_client.call_tool(tool_name, tool_args)  # type: ignore
        prompt_messages = await self.generate_prompt_template(
            response_message.tool_calls[0].function.name,
            tool_response,  # type: ignore
            user_input=message["content"],  # type: ignore
        )
        # 加入 prompt
        self.messages = deepcopy(memory)  # 在记忆中隔离 tool 上下文。 # type: ignore[assignment]
        if prompt_messages != []:
            self.messages.extend(prompt_messages)

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
        stream = await self.openai_client.chat.completions.create(  # type: ignore[return-value]
            model=self.config.agent.llm.gemini.llm_model_name,
            messages=self.messages,  # type: ignore[assignment]
            stream=True,
        )
        async for chunk in stream:  # type: ignore[assignment]
            if chunk.choices[0].delta.content is None:  # type: ignore[assignment]
                chunk.choices[0].delta.content = ""  # type: ignore[assignment]
            yield chunk.choices[0].delta.content  # type: ignore[assignment]
