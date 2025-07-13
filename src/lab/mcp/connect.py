from __future__ import annotations

from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


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
