from __future__ import annotations

from contextlib import AsyncExitStack

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from loguru import logger


class FastMcpRouter:
    """
    FastMCP multi-server router：
    - connect(): 连接并保持长连接（AsyncExitStack 挂住 client）
    - list_tools_openai_schema(): 生成 OpenAI tools schema
    - call_tool() / get_prompt(): 按 namespace 路由
    """

    def __init__(self, *, prefix_delim: str = "__") -> None:
        self.prefix_delim = prefix_delim
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}  # type: ignore

    async def connect(self, *, name: str, url: str, headers: dict[str, str] | None = None) -> None:
        """
        连接 MCP server（HTTP/Streamable HTTP）。

        headers 输入示例：
            {"Authorization":"Bearer xxx"}

        成功后会 log：
            [MCP] connected timeemi tools=2 url=http://127.0.0.1:4200/
        """
        transport = StreamableHttpTransport(url=url, headers=headers)
        client = Client(transport)
        client = await self._stack.enter_async_context(client)
        self._clients[name] = client  # type: ignore

        tools = await client.list_tools()
        logger.info(f"[MCP] connected {name} tools={len(tools)} url={url}")

    async def close(self) -> None:
        """关闭所有连接。"""
        await self._stack.aclose()

    async def list_tools_openai_schema(self) -> list[dict[str, object]]:
        """
        合并所有 server 的 tools，转换成 OpenAI tools schema（list[dict]）。

        输出示例：
            [
              {"type":"function","function":{"name":"timeemi__roll_dice","description":"...","parameters":{...}}}
            ]
        """
        out: list[dict[str, object]] = []
        for server, client in self._clients.items():  # type: ignore
            tools = await client.list_tools()
            for t in tools:
                full_name = f"{server}{self.prefix_delim}{t.name}"
                out.append(
                    {
                        "type": "function",
                        "function": {
                            "name": full_name,
                            "description": t.description or "",
                            "parameters": t.inputSchema or {"type": "object", "properties": {}},
                        },
                    }
                )
        return out

    def _split(self, full_name: str) -> tuple[str, str]:
        server, tool = full_name.split(self.prefix_delim, 1)
        return server, tool

    async def call_tool(self, *, full_name: str, args: dict[str, object]) -> object:
        """
        调用工具（raise_on_error=False，交给上层统一处理）。

        args 输入示例：
            {"n_dice": 3}
        """
        server, tool = self._split(full_name)
        client = self._clients[server]  # type: ignore
        return await client.call_tool(tool, args, raise_on_error=False)

    async def get_prompt(self, *, full_name: str, prompt_name: str, args: dict[str, object]) -> object:
        """
        获取 server 侧 prompt 模板文本。

        args 输入示例：
            {"time_str": "2026-01-27 20:54:37"}
        """
        server, _ = self._split(full_name)
        client = self._clients[server]  # type: ignore
        return await client.get_prompt(prompt_name, args)
