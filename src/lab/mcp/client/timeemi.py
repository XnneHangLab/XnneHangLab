from __future__ import annotations

import asyncio

# from typing import Any
import json

from mcp.types import CallToolResult

from lab.mcp._typing import CommonMessage, ToolMessage
from lab.mcp.example.openai_client import read_prompt_from_mcp_prompt_template, read_result_from_mcp_tool_response, read_prompt_from_text_file

from lab.mcp.connect import MCPConnection
from lab.mcp.client.base_mcp_interface import MCPHandlerInterface


class TimeeiMCPHandler(MCPHandlerInterface):
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

    async def generate_prompt_template(self, tool_name: str, tool_response: CallToolResult,user_input:str) -> list[CommonMessage]:
        messages: list[CommonMessage] = []
        if tool_name == "get_date_and_time":
            prompt_response = await self.mcp_client.get_prompt(
                "convert_time_readable", {"time_str": read_result_from_mcp_tool_response(tool_response)}
            )
            messages.append(CommonMessage(role="user",content=read_prompt_from_mcp_prompt_template(prompt_response)))
            prompt_response = await self.mcp_client.get_prompt(
                "limit_time_response", {"user_input":user_input}
            )
            messages.append(CommonMessage(role="user",content=read_prompt_from_mcp_prompt_template(prompt_response)))

        if tool_name == "roll_dice":
            prompt_response = await self.mcp_client.get_prompt(
                "convert_list_int_readable", {"numbers": read_result_from_mcp_tool_response(tool_response)}
            )
            messages.append(CommonMessage(role="user",content=read_prompt_from_mcp_prompt_template(prompt_response)))
        return messages

    async def process(self,message:CommonMessage, memory:list[CommonMessage]):  # type: ignore[override]
        self.messages = self.reset_messages()
        self.messages.append(message)
        print(self.messages)
        response = await self.openai_client.chat.completions.create(  # type: ignore[return-value]
            model=self.config.agent.llm.gemini.llm_model_name,
            messages=self.messages,  # type: ignore[assignment]
            tools=self.available_tools,  # type: ignore[assignment]
            tool_choice="auto",  # 让模型自行决定是否调用工具
        )
        response_message = response.choices[0].message

        if not response_message.tool_calls: # 对于 tool call stream response 的屈服。宁可多调用一次也不能放弃 stream。
            print("no tool call")
            self.messages = memory # type:ignore
            self.messages.append(message)
            stream = await self.openai_client.chat.completions.create(  # type: ignore[return-value]
                model=self.config.agent.llm.gemini.llm_model_name,
                messages=self.messages,  # type: ignore[assignment]
                stream=True
            )
            async for chunk in stream:  # type: ignore[assignment]
                if chunk.choices[0].delta.content is None:  # type: ignore[assignment]
                    chunk.choices[0].delta.content = ""  # type: ignore[assignment]
                yield chunk.choices[0].delta.content  # type: ignore[assignment]
        else:
            print("tool call")
            # 生成Prompt模板并且加入 messages
            tool_name = response_message.tool_calls[0].function.name  # TODO 也许能实现多个 tool 的功能？但是可能过于复杂暂时不考虑
            tool_args = json.loads(response_message.tool_calls[0].function.arguments)
            tool_response = await self.mcp_client.call_tool(tool_name, tool_args)
            prompt_messages = await self.generate_prompt_template(response_message.tool_calls[0].function.name, tool_response,user_input=message["content"])
            # 加入 prompt
            self.messages = memory # 在记忆中隔离 tool 上下文。 # type: ignore[assignment]
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
            stream = await self.openai_client.chat.completions.create( # type: ignore[return-value]
                model=self.config.agent.llm.gemini.llm_model_name,
                messages=self.messages,  # type: ignore[assignment]
                stream=True,
            )
            async for chunk in stream:  # type: ignore[assignment]
                if chunk.choices[0].delta.content is None:  # type: ignore[assignment]
                    chunk.choices[0].delta.content = ""  # type: ignore[assignment]
                yield chunk.choices[0].delta.content  # type: ignore[assignment]


async def main():
    async with MCPConnection("src/lab/mcp/server/timeemi.py") as session:
        mcp_handler = await TimeeiMCPHandler.create(session)
        memory = [CommonMessage(role="system",content=read_prompt_from_text_file("elaina"))]
        async for chunk in mcp_handler.process(message=CommonMessage(role="user", content="你今天真可爱"),memory=memory): # type: ignore
            print(chunk) # type: ignore
        print(mcp_handler.messages)


if __name__ == "__main__":
    asyncio.run(main())