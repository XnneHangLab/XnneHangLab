from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from typing import Optional

from dotenv import load_dotenv
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

load_dotenv()


class MCPClient:
    def __init__(self):
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.client = OpenAI(
            base_url=self.config.agent.llm.gemini.llm_base_url, api_key=self.config.agent.llm.gemini.llm_api_key
        )

    async def connect_to_server(self):
        server_params = StdioServerParameters(command="uv", args=["run", "src/lab/mcp/server.py"], env=None)

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))

        await self.session.initialize()

    async def chat(self, query: str) -> str:
        system_prompt = (
            "You are a helpful assistant with access to tools. Use tools when needed but maintain natural conversation."
        )

        messages = [{"role": "system", "content": system_prompt}]

        # 添加用户消息
        messages.append({"role": "user", "content": query})

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

            response = await client.chat.completions.create(
                model=self.config.agent.llm.gemini.llm_model_name,
                messages=messages,
                tools=available_tools,
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
                result = await self.session.call_tool(tool_name, tool_args)
                if tool_name == "get_date_and_time":
                    # 添加一些提示词:
                    convert_prompt = await self.session.get_prompt(
                        "convert_time_readable", {"time_str": str(result.content[0].text)}
                    )
                    messages.append({"role": "user", "content": convert_prompt.messages[0].content.text})
                    print("=======convert_prompt========")
                    print(convert_prompt)

                # 将结果添加到消息历史
                messages.append(response_message)
                messages.append(
                    {
                        "role": "tool",
                        "content": result.content[0].text,
                        "tool_call_id": tool_call.id,
                    }
                )

                # 获取最终响应
                second_response = await client.chat.completions.create(
                    model=self.config.agent.llm.gemini.llm_model_name, messages=messages
                )
                return second_response.choices[0].message.content

            return response_message.content

        except (APIConnectionError, APIError, RateLimitError) as e:
            # 处理API错误
            return f"Sorry, I encountered an error: {str(e)}"

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    client = MCPClient()
    try:
        await client.connect_to_server()
        response = await client.chat("明天是几月几号？")
        print(response)
        response = await client.chat("我晚上九点就后就该去打游戏了，现在几点？")
        print(response)
        response = await client.chat("帮我随便roll三个点数")
        print(response)
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
