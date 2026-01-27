from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Protocol

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from loguru import logger
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError

from lab.config_manager import XnneHangLabSettings, load_settings_file


# -----------------------------
# Minimal typing for tool_calls (OpenAI tool calling)
# -----------------------------
class _FnLike(Protocol):
    name: str
    arguments: str | None


class ToolCallLike(Protocol):
    id: str
    function: _FnLike


def _dump_msg(obj: Any) -> dict[str, Any]:
    """兼容 OpenAI SDK：优先 model_dump，其次 to_dict。"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(f"Unknown message type: {type(obj)}")


def _prompt_result_to_text(prompt_result: Any) -> str:
    """
    FastMCP client.get_prompt() -> GetPromptResult，里面有 messages 列表。:contentReference[oaicite:2]{index=2}
    这里把所有 message 拼成一个文本，作为下一轮 Tool Model 的 user 输入。
    """
    msgs = getattr(prompt_result, "messages", None) or []
    lines: list[str] = []
    for m in msgs:
        role = getattr(m, "role", "unknown")
        content = getattr(m, "content", "")
        # content 可能是 TextContent，也可能是 str
        text = getattr(content, "text", None)
        if text is None:
            text = str(content)
        lines.append(f"{role}: {text}")
    return "\n".join(lines).strip()


def _calltool_result_to_text(result: Any) -> str:
    """
    FastMCP call_tool() 返回 CallToolResult：
    - result.data：反序列化后的 python 对象/原始值（FastMCP 独有增强）
    - result.content：标准 MCP content blocks
    - result.is_error：是否错误
    详见文档。:contentReference[oaicite:3]{index=3}
    """
    if getattr(result, "is_error", False):
        # 尽量把错误文本吐出来
        content_blocks = getattr(result, "content", None) or []
        for c in content_blocks:
            t = getattr(c, "text", None)
            if t:
                return t
        return "tool_error"

    data = getattr(result, "data", None)
    if data is not None:
        # data 可能是 int/str/bool/obj
        if isinstance(data, (str, int, float, bool)):
            return str(data)
        # 复杂对象：转 json 字符串
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            return str(data)

    # fallback：读 content blocks
    content_blocks = getattr(result, "content", None) or []
    texts: list[str] = []
    for c in content_blocks:
        t = getattr(c, "text", None)
        if t:
            texts.append(t)
    return "\n".join(texts).strip() or "tool_ok"


# -----------------------------
# FastMCP multi-server router
# -----------------------------
class FastMcpRouter:
    def __init__(self, *, prefix_delim: str = "__") -> None:
        self.prefix_delim = prefix_delim
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}

    async def connect(self, *, name: str, url: str, headers: dict[str, str] | None = None) -> None:
        """
        用 FastMCP Client + StreamableHttpTransport 连接 MCP server。
        FastMCP client 会自动处理协议细节。:contentReference[oaicite:4]{index=4}
        """
        transport = StreamableHttpTransport(url=url, headers=headers)
        client = Client(transport)

        # 关键点：要保持连接可用，必须把 client 的 async context “挂住”
        # 否则 async with 退出后连接就关了（你之前 _async_init 那样会导致后续 call_tool 失效）
        client = await self._stack.enter_async_context(client)
        self._clients[name] = client

        # 验证一下能 list_tools（顺便让连接在这里就报错）
        tools = await client.list_tools()  # :contentReference[oaicite:5]{index=5}
        logger.info(f"[MCP] connected {name} tools={len(tools)} url={url}")

    async def close(self) -> None:
        await self._stack.aclose()

    async def list_tools_openai_schema(self) -> list[dict[str, Any]]:
        """
        把多个 server 的工具合并成 OpenAI tools schema，并加 namespace 前缀。
        FastMCP tools 里 tool.inputSchema/tool.description/tool.name 都可用。:contentReference[oaicite:6]{index=6}
        """
        out: list[dict[str, Any]] = []
        for server_name, client in self._clients.items():
            tools = await client.list_tools()
            for tool in tools:
                full_name = f"{server_name}{self.prefix_delim}{tool.name}"
                out.append(
                    {
                        "type": "function",
                        "function": {
                            "name": full_name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                        },
                    }
                )
        return out

    def _split(self, full_name: str) -> tuple[str, str]:
        server, tool = full_name.split(self.prefix_delim, 1)
        return server, tool

    async def call_tool(self, *, full_name: str, args: dict[str, Any]) -> Any:
        server, tool = self._split(full_name)
        client = self._clients[server]
        # raise_on_error=False：我们自己处理 is_error，避免异常打断 tool loop。:contentReference[oaicite:7]{index=7}
        return await client.call_tool(tool, args, raise_on_error=False)

    async def get_prompt(self, *, full_name: str, prompt_name: str, args: dict[str, Any]) -> Any:
        server, _ = self._split(full_name)
        client = self._clients[server]
        return await client.get_prompt(prompt_name, args)  # :contentReference[oaicite:8]{index=8}


# -----------------------------
# Agent: Tool loop (non-stream) + Chat (stream)
# -----------------------------
class Agent:
    def __init__(self) -> None:
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)

        # 兼容你之前的结构：tool_model / chat_model（如果你现在配置不一样，自行对齐字段）
        tool_model = self.config.agent.tool_model
        chat_model = self.config.agent.chat_model
        tool_llm_setting = getattr(self.config.agent.llm, tool_model.llm_provider)
        chat_llm_setting = getattr(self.config.agent.llm, chat_model.llm_provider)

        self.tool_client = AsyncOpenAI(base_url=tool_llm_setting.llm_base_url, api_key=tool_llm_setting.llm_api_key)
        self.chat_client = AsyncOpenAI(base_url=chat_llm_setting.llm_base_url, api_key=chat_llm_setting.llm_api_key)

        self.tool_model_name = tool_model.llm_model_name
        self.chat_model_name = chat_model.llm_model_name

        self.mcp = FastMcpRouter(prefix_delim="__")

    def _load_system_prompt(self) -> str:
        system_prompt_path = Path("prompts") / "characters" / f"{self.config.agent.character_name}.txt"
        system_prompt = system_prompt_path.read_text(encoding="utf-8") if system_prompt_path.exists() else ""
        system_prompt += "\n\n**請使用和用戶相同的語言**"
        return system_prompt

    async def connect_mcp_servers(self) -> None:
        # 用你已确认能连接的 FastMCP Client 方式
        await self.mcp.connect(name="timeemi", url="http://127.0.0.1:4200/")  # 你现在 server path="/"
        await self.mcp.connect(name="vision", url="http://127.0.0.1:4201/")

    async def close(self) -> None:
        await self.mcp.close()

    async def _execute_tool_call(
        self,
        tool_call: ToolCallLike,
        *,
        tool_output_as_user_prompt: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        full_name = tool_call.function.name
        args: dict[str, Any] = json.loads(tool_call.function.arguments or "{}")

        result = await self.mcp.call_tool(full_name=full_name, args=args)
        tool_text = _calltool_result_to_text(result)

        tool_msg: dict[str, Any] = {"role": "tool", "content": tool_text, "tool_call_id": tool_call.id}

        server, tool_name = full_name.split("__", 1)
        trace_item: dict[str, Any] = {"server": server, "name": tool_name, "args": args, "result": tool_text}

        extra_msgs: list[dict[str, Any]] = []
        if tool_output_as_user_prompt:
            # 你原本的“可读化 prompt”逻辑：用 server-side prompt 生成下一轮 Tool Model 的 user input
            if tool_name == "get_date_and_time":
                pr = await self.mcp.get_prompt(
                    full_name=full_name, prompt_name="convert_time_readable", args={"time_str": tool_text}
                )
                extra_msgs.append({"role": "user", "content": _prompt_result_to_text(pr)})

            elif tool_name == "roll_dice":
                pr = await self.mcp.get_prompt(
                    full_name=full_name, prompt_name="convert_list_int_readable", args={"numbers": tool_text}
                )
                extra_msgs.append({"role": "user", "content": _prompt_result_to_text(pr)})

        return tool_msg, extra_msgs, trace_item

    async def run_tool_loop(
        self,
        *,
        system_prompt: str,
        user_input: str,
        available_tools: list[dict[str, Any]],
        max_steps: int = 6,
        max_parallel_tools: int = 6,
        debug: bool = True,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Tool Model：非流式
        - 并行：同轮多个 tool_calls -> gather
        - 链式：tool 输出 + extra prompt 回填 messages -> 下一轮继续决策
        """
        tool_loop_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        tool_trace: list[dict[str, Any]] = []

        for step in range(max_steps):
            resp = await self.tool_client.chat.completions.create(
                model=self.tool_model_name,
                messages=tool_loop_messages,
                tools=available_tools,
                tool_choice="auto",
                stream=False,  # ✅ Tool Model 非流式
            )

            assistant_msg = resp.choices[0].message
            tool_loop_messages.append(_dump_msg(assistant_msg))

            tool_calls = getattr(assistant_msg, "tool_calls", None)
            if debug:
                names = [tc.function.name for tc in (tool_calls or [])]
                logger.info(f"[ToolLoop step={step}] tool_calls={names}")

            if not tool_calls:
                break

            tool_calls = list(tool_calls)[:max_parallel_tools]
            results = await asyncio.gather(*[self._execute_tool_call(tc) for tc in tool_calls])

            for tool_msg, extra_msgs, trace_item in results:
                tool_loop_messages.append(tool_msg)
                tool_trace.append(trace_item)
                tool_loop_messages.extend(extra_msgs)

        return tool_loop_messages, tool_trace

    async def stream_chat_answer(
        self,
        *,
        system_prompt: str,
        user_input: str,
        tool_trace: list[dict[str, Any]],
    ):
        """
        Chat Model：流式输出最终回复（不做 tool calling）
        """
        tool_summary = json.dumps(tool_trace, ensure_ascii=False, indent=2) if tool_trace else "[]"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"以下是工具调用摘要（可直接引用）：\n{tool_summary}"},
            {"role": "user", "content": user_input},
        ]

        stream = await self.chat_client.chat.completions.create(
            model=self.chat_model_name,
            messages=messages,
            stream=True,  # ✅ Chat Model 流式
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                yield delta.content

    async def chat_stream(self, user_input: str, *, debug: bool = True):
        system_prompt = self._load_system_prompt()
        available_tools = await self.mcp.list_tools_openai_schema()

        # 1) Tool loop（非流式、可并行、可链式）
        _, tool_trace = await self.run_tool_loop(
            system_prompt=system_prompt,
            user_input=user_input,
            available_tools=available_tools,
            debug=debug,
        )

        if debug:
            logger.info("[ToolTrace]")
            for t in tool_trace:
                logger.info(f"  - {t['server']}::{t['name']} args={t['args']} -> {t['result']}")

        # 2) Chat model（流式最终回复）
        async for tok in self.stream_chat_answer(system_prompt=system_prompt, user_input=user_input, tool_trace=tool_trace):
            yield tok


async def main():
    agent = Agent()
    try:
        await agent.connect_mcp_servers()

        async def run(q: str):
            print(f"\n\n=== Q: {q} ===")
            try:
                async for tok in agent.chat_stream(q, debug=True):
                    print(tok, end="", flush=True)
                print("\n=== END ===")
            except (APIConnectionError, APIError, RateLimitError) as e:
                print(f"\n[LLM error] {e}")

        # await run("昨天几号？")
        await run("今、何時ですか？")
        # await run("我晚上九点就后就该去打游戏了，现在几点？")
        await run("帮我随便roll三个点数")
        # await run("你今天真可爱")

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
