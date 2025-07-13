# as an example for openai client, 不在实际环境中使用, 但这个是我们最终使用的方案。
from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import (
    APIConnectionError,
    APIError,
    AsyncOpenAI,
    OpenAI,
    # AsyncStream,
    RateLimitError,
)

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.mcp.util import read_prompt_from_mcp_prompt_template, read_result_from_mcp_tool_response


class MCPClient:
    def __init__(self):
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self.client = OpenAI(
            base_url=self.config.agent.llm.gemini.llm_base_url, api_key=self.config.agent.llm.gemini.llm_api_key
        )

    async def connect_to_server(self):
        server_params = StdioServerParameters(command="uv", args=["run", "src/lab/mcp/server/timeemi.py"], env=None)

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))

        await self.session.initialize()

    async def chat(self, user_input: str) -> str:
        print("====== user_input ======")
        print(user_input)
        system_prompt_path = Path("prompts") / f"{self.config.agent.system_prompt_name}.txt"
        with system_prompt_path.open("r", encoding="utf-8") as f:
            system_prompt = f.read()
        system_prompt = "\n**請使用和用戶相同的語言**"

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        # 添加用户消息
        messages.append({"role": "user", "content": user_input})

        # 获取可用工具列表
        if self.session is None:
            raise ValueError("session is not initialized")
        tool_list = await self.session.list_tools()

        # 转换为OpenAI格式的工具描述
        available_tools = [
            {
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": tool.inputSchema},
            }
            for tool in tool_list.tools
        ]

        # 使用AsyncOpenAI进行对话
        try:
            client = AsyncOpenAI(
                base_url=self.config.agent.llm.gemini.llm_base_url, api_key=self.config.agent.llm.gemini.llm_api_key
            )

            response = await client.chat.completions.create(  # type: ignore[return-value]
                model=self.config.agent.llm.gemini.llm_model_name,
                messages=messages,  # type: ignore[assignment]
                tools=available_tools,  # type: ignore[assignment]
                tool_choice="auto",  # 让模型自行决定是否调用工具
            )

            response_message = response.choices[0].message

            # 检查是否需要调用工具
            if response_message.tool_calls:
                # 处理工具调用
                tool_call = response_message.tool_calls[0]
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # 执行工具
                tool_response = await self.session.call_tool(tool_name, tool_args)
                # 添加一些提示词:
                # TODO 在实际应用场景中，要考虑清理这些 prompt 不留在长期记忆中占 token 数量
                if tool_name == "get_date_and_time":
                    prompt_response = await self.session.get_prompt(
                        "convert_time_readable", {"time_str": read_result_from_mcp_tool_response(tool_response)}
                    )
                    messages.append({"role": "user", "content": read_prompt_from_mcp_prompt_template(prompt_response)})
                    print("======= add_prompt ========")
                    print(read_prompt_from_mcp_prompt_template(prompt_response))
                if tool_name == "roll_dice":
                    prompt_response = await self.session.get_prompt(
                        "convert_list_int_readable", {"numbers": read_result_from_mcp_tool_response(tool_response)}
                    )
                    messages.append({"role": "user", "content": read_prompt_from_mcp_prompt_template(prompt_response)})
                    print("======= add_prompt ========")
                    print(read_prompt_from_mcp_prompt_template(prompt_response))

                # 将结果添加到消息历史
                messages.append(response_message.to_dict())
                messages.append(
                    {
                        "role": "tool",
                        "content": read_result_from_mcp_tool_response(tool_response),
                        "tool_call_id": tool_call.id,
                    }
                )

                # 获取最终响应
                second_response = await client.chat.completions.create(
                    model=self.config.agent.llm.gemini.llm_model_name,
                    messages=messages,  # type: ignore[assignment]
                )
                if second_response.choices[0].message.content:
                    return second_response.choices[0].message.content
                else:
                    return "second call tool return None"
            if response_message.content:
                return response_message.content
            else:
                return "response content return None"

        except (APIConnectionError, APIError, RateLimitError) as e:
            # 处理API错误
            return f"error: {str(e)}, 请检查网络连接或者 api key 与 base url"

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    client = MCPClient()
    try:
        await client.connect_to_server()
        response = await client.chat("昨天几号？")
        print(response)
        response = await client.chat("今、何時ですか？")
        print(response)
        response = await client.chat("我晚上九点就后就该去打游戏了，现在几点？")
        print(response)
        response = await client.chat("帮我随便roll三个点数")
        print(response)
        response = await client.chat("你今天真可爱")
        print(response)
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
