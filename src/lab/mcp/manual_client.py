# as an example for manual call tools, 不在实际环境中使用。
from __future__ import annotations

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 为 stdio 连接创建服务器参数
server_params = StdioServerParameters(
    # 服务器执行的命令，这里我们使用 uv 来运行 web_search.py
    command="uv",
    # 运行的参数
    args=["run", "src/lab/mcp/server.py"],
    # 环境变量，默认为 None，表示使用当前环境变量
    # env=None
)


async def main():
    # 创建 stdio 客户端
    async with stdio_client(server_params) as (stdio, write):
        # 创建 ClientSession 对象
        async with ClientSession(stdio, write) as session:
            # 初始化 ClientSession
            await session.initialize()

            # 列出可用的工具
            response = await session.list_tools()
            print(response)

            # 手动调用工具
            response = await session.call_tool("get_date_and_time")
            print(response)

            # 读取 prompt
            prompt_1 = await session.get_prompt("convert_time_readable", {"time_str": str(response.content[0].text)})  # type: ignore
            print(prompt_1)
            prompt_2 = await session.get_prompt(
                "limit_time_response",
                {"time_str": "二零零四年十月十四日，十二时二十一分四十一秒", "ask": "现在几点了？"},
            )
            print(prompt_2)


if __name__ == "__main__":
    asyncio.run(main())
