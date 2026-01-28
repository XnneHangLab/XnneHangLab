from __future__ import annotations

import asyncio
import json
import random
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from loguru import logger
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from lab.config_manager import XnneHangLabSettings, load_settings_file


# =============================================================================
# 1) OpenAI tool calling：最小 Protocol（SDK 边界）
# =============================================================================
class _FnLike(Protocol):
    name: str
    arguments: str | None


class ToolCallLike(Protocol):
    id: str
    function: _FnLike


def dump_openai_msg(obj: object) -> dict[str, object]:
    """
    将 OpenAI SDK 返回的 message 对象 dump 成 dict。

    说明：
    - 这是 SDK 边界：OpenAI SDK 对象类型复杂，这里用 hasattr 兼容。
    - 其它地方尽量用 pydantic BaseModel 强类型。

    输出示例：
        {"role": "assistant", "content": "...", "tool_calls": [...], ...}
    """
    if hasattr(obj, "model_dump"):
        d = obj.model_dump(exclude_none=True)  # type: ignore[attr-defined]
        return dict(d) # type: ignore
    if hasattr(obj, "to_dict"):
        d = obj.to_dict()  # type: ignore[attr-defined]
        return dict(d) # type: ignore
    raise TypeError(f"Unknown message type: {type(obj)}")


# =============================================================================
# 2) 我们自己构造的 message / trace（IDE 可补全）
# =============================================================================
class OpenAIMessage(BaseModel):
    """
    我们自己构造的 OpenAI message。

    示例：
        {"role": "system", "content": "你是一个助手"}
        {"role": "user", "content": "现在几点？"}
        {"role": "tool", "content": "...", "tool_call_id": "call_xxx"}
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None


class ToolMessage(BaseModel):
    """
    OpenAI tool message：回填给 Tool Model。

    示例：
        {"role": "tool", "content": "2026-01-27 20:54:37", "tool_call_id": "call_xxx"}
    """

    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str


class ToolTraceItem(BaseModel):
    """
    给 Chat Model 的工具调用摘要（结构化）。

    注意：为了让 Chat Model 更好地“口语化 + TTS友好”，建议保留：
    - raw_result：原始结果（可用于精确计算）
    - display_hint：你希望 Chat Model 展示/口语化的方向（可选）

    示例：
        {
          "server":"timeemi",
          "name":"get_date_and_time",
          "args":{},
          "raw_result":{"datetime":"2026-01-27 20:54:37"},
          "ok": true
        }
    """

    server: str
    name: str
    args: dict[str, object] = Field(default_factory=dict)
    raw_result: dict[str, object] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None


# =============================================================================
# 3) 已知工具：Args / Result（pydantic 强校验）
# =============================================================================
_TIME_RE = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"


class GetDateAndTimeArgs(BaseModel):
    """
    timeemi.get_date_and_time 入参（无参数）。

    输入示例：
        {}
    """

    model_config = ConfigDict(extra="forbid")


class GetDateAndTimeResult(BaseModel):
    """
    timeemi.get_date_and_time 输出。

    输出示例：
        {"datetime": "2026-01-27 20:54:37"}
    """

    datetime: str = Field(..., description="YYYY-MM-DD HH:MM:SS")

    @field_validator("datetime")
    @classmethod
    def _check_fmt(cls, v: str) -> str:
        import re

        vv = v.strip()
        if not re.match(_TIME_RE, vv):
            raise ValueError(f"bad datetime format: {v!r}")
        return vv


class RollDiceArgs(BaseModel):
    """
    timeemi.roll_dice 入参。

    输入示例：
        {"n_dice": 3}
    """

    model_config = ConfigDict(extra="forbid")
    n_dice: int = Field(..., ge=1, le=50, description="骰子数量（建议限制，防止滥用）")


class RollDiceResult(BaseModel):
    """
    timeemi.roll_dice 输出。

    输出示例：
        {"numbers": [5, 3, 1]}
    """

    numbers: list[int]

    @field_validator("numbers")
    @classmethod
    def _check_range(cls, v: list[int]) -> list[int]:
        for x in v:
            if x < 1 or x > 6:
                raise ValueError(f"dice out of range: {x}")
        return v


class UnknownArgs(BaseModel):
    """
    未知工具入参（扩展点）。

    说明：
    - 动态工具不强求 IDE 补全
    - 仍然做最基本的“必须是 dict”约束

    输入示例：
        {"k":"v"}
    """

    data: dict[str, object] = Field(default_factory=dict)


class UnknownResult(BaseModel):
    """
    未知工具输出（扩展点）。

    输出示例：
        {"data": ...}
    """

    data: object | None = None


# =============================================================================
# 4) ToolRegistry：强类型解析入口（你以后扩展就在这里加分支）
# =============================================================================
@dataclass(frozen=True)
class ParsedTool:
    """
    { full_name: timeemi__get_date_and_time,
      server: timeemi,
      name: get_date_and_time,
      args_model: GetDateAndTimeArgs
    }
    """
    full_name: str
    server: str
    name: str
    args_model: BaseModel


class ToolRegistry:
    """
    工具注册表（强类型入口）。

    你要扩展新工具，照着已有分支加：
    - Args(BaseModel)
    - Result(BaseModel)
    - parse_args / parse_result 各加一个 elif
    """

    @staticmethod
    def parse_args(full_name: str, arguments_json: str | None) -> ParsedTool:
        """
        解析 tool_call.arguments（JSON 字符串）为对应 Args(BaseModel)。

        输入示例：
            full_name="timeemi__roll_dice"
            arguments_json='{"n_dice": 3}'

        输出示例：
            ParsedTool(..., args_model=RollDiceArgs(n_dice=3))
        """
        server, name = full_name.split("__", 1)
        s = arguments_json or "{}"

        if full_name == "timeemi__get_date_and_time":
            args_model = GetDateAndTimeArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)

        if full_name == "timeemi__roll_dice":
            args_model = RollDiceArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)

        # 未知工具：保底当 dict
        try:
            raw = json.loads(s)
            if not isinstance(raw, dict):
                raw = {}
        except Exception:
            raw = {}
        args_model = UnknownArgs(data=raw) # type: ignore
        return ParsedTool(full_name, server, name, args_model)

    @staticmethod
    def parse_result(full_name: str, call_tool_result: object) -> BaseModel:
        """
        将 FastMCP call_tool 返回转成 Result(BaseModel)。

        说明：
        - 若 is_error=True，则返回 UnknownResult(data=错误文本)
        - 否则优先读取 result.data（FastMCP 已反序列化）

        已知工具强校验：
        - get_date_and_time: data 必须是 str 且符合格式
        - roll_dice: data 必须是 list[int] 且 1..6
        """
        is_error = bool(getattr(call_tool_result, "is_error", False))
        if is_error:
            # 尽量提取错误文本
            blocks = getattr(call_tool_result, "content", None) or [] # type: ignore
            err_text = None
            for b in blocks: # type: ignore
                t = getattr(b, "text", None) # type: ignore
                if t:
                    err_text = t
                    break
            return UnknownResult(data=err_text or "tool_error")

        data = getattr(call_tool_result, "data", None)

        if full_name == "timeemi__get_date_and_time":
            if not isinstance(data, str):
                raise TypeError(f"timeemi.get_date_and_time expects str, got {type(data)}")
            return GetDateAndTimeResult(datetime=data)

        if full_name == "timeemi__roll_dice":
            if not (isinstance(data, list) and all(isinstance(x, int) for x in data)): # type: ignore
                raise TypeError(f"timeemi.roll_dice expects list[int], got {type(data)} {data}") # type: ignore
            return RollDiceResult(numbers=data) # type: ignore

        return UnknownResult(data=data)

    @staticmethod
    def tool_content_for_tool_model(full_name: str, result_model: BaseModel) -> str:
        """
        生成回填给 Tool Model 的 tool message content（尽量短）。

        注意：你不希望 client 侧做口语化，所以这里返回“原始但简短”的值。

        输出示例：
            "2026-01-27 20:54:37"
            "[5, 3, 1]"
        """
        if isinstance(result_model, GetDateAndTimeResult):
            return result_model.datetime
        if isinstance(result_model, RollDiceResult):
            return json.dumps(result_model.numbers, ensure_ascii=False)
        d = result_model.model_dump(exclude_none=True)
        return json.dumps(d, ensure_ascii=False, default=str)

    @staticmethod
    def trace_item(parsed: ParsedTool, result_model: BaseModel, *, ok: bool, error: str | None) -> ToolTraceItem:
        """
        构造结构化 trace（给 Chat Model）。

        - args：Args(BaseModel) dump 成 dict
        - raw_result：Result(BaseModel) dump 成 dict
        """
        args_dict = parsed.args_model.model_dump(exclude_none=True)
        raw_dict = result_model.model_dump(exclude_none=True)
        return ToolTraceItem(
            server=parsed.server,
            name=parsed.name,
            args=args_dict,
            raw_result=raw_dict,
            ok=ok,
            error=error,
        )


# =============================================================================
# 5) Prompt helpers（FastMCP GetPromptResult -> str）
# =============================================================================
def prompt_result_to_text(prompt_result: object) -> str:
    """
    FastMCP client.get_prompt() 的返回通常包含 messages 列表，这里拼成纯文本。

    输出示例：
        "system: ...\nuser: ...\nassistant: ..."
    """
    msgs = getattr(prompt_result, "messages", None) or [] # type: ignore
    lines: list[str] = []
    for m in msgs: # type: ignore
        role = getattr(m, "role", "unknown") # type: ignore
        content = getattr(m, "content", "") # type: ignore
        text = getattr(content, "text", None) # type: ignore
        if text is None:
            text = str(content)
        lines.append(f"{role}: {text}")
    return "\n".join(lines).strip()


# =============================================================================
# 6) FastMCP Router（多 server）
# =============================================================================
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
        self._clients: dict[str, Client] = {} # type: ignore

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
        self._clients[name] = client # type: ignore

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
        for server, client in self._clients.items(): # type: ignore
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
        client = self._clients[server] # type: ignore
        return await client.call_tool(tool, args, raise_on_error=False)

    async def get_prompt(self, *, full_name: str, prompt_name: str, args: dict[str, object]) -> object:
        """
        获取 server 侧 prompt 模板文本。

        args 输入示例：
            {"time_str": "2026-01-27 20:54:37"}
        """
        server, _ = self._split(full_name)
        client = self._clients[server] # type: ignore
        return await client.get_prompt(prompt_name, args)


# =============================================================================
# 7) 轻量重试（仅针对 429 queue_exceeded，避免你高峰期直接炸）
# =============================================================================
async def call_with_short_retry(awaitable_factory, *, max_retries: int = 2): # type: ignore
    """
    仅对 429 queue_exceeded 做短重试（避免明显变慢）。
    - 正常成功：零额外开销
    - 遇到 queue_exceeded：最多重试 2 次，总等待通常 < 1.5s
    """
    last: Exception | None = None
    for i in range(max_retries + 1):
        try:
            return await awaitable_factory() # type: ignore
        except (RateLimitError, APIError) as e:
            last = e
            msg = str(e)
            if "429" not in msg or "queue_exceeded" not in msg:
                raise
            if i == max_retries:
                raise
            sleep_s = (0.25 * (2**i)) + random.uniform(0.0, 0.2)
            await asyncio.sleep(sleep_s)
    raise last  # pragma: no cover # type: ignore


# =============================================================================
# 8) Agent：Tool loop（非流式）+ Chat（流式）
# =============================================================================
class Agent:
    """
    Agent 行为：
    - Tool Model（非流式）：决定是否调用工具；支持并行 tool_calls；支持链式多轮
    - Chat Model（流式）：使用 tool_trace 摘要产出最终回复（口语化交给它）
    """

    def __init__(self) -> None:
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)

        tool_model = self.config.agent.tool_model
        chat_model = self.config.agent.chat_model
        tool_llm = getattr(self.config.agent.llm, tool_model.llm_provider)
        chat_llm = getattr(self.config.agent.llm, chat_model.llm_provider)

        self.tool_client = AsyncOpenAI(base_url=tool_llm.llm_base_url, api_key=tool_llm.llm_api_key)
        self.chat_client = AsyncOpenAI(base_url=chat_llm.llm_base_url, api_key=chat_llm.llm_api_key)

        self.tool_model_name = tool_model.llm_model_name
        self.chat_model_name = chat_model.llm_model_name

        self.mcp = FastMcpRouter(prefix_delim="__")

    def _load_system_prompt(self) -> str:
        """
        加载角色系统提示词。
        """
        p = Path("prompts") / "characters" / f"{self.config.agent.character_name}.txt"
        system = p.read_text(encoding="utf-8") if p.exists() else ""
        system += "\n\n**請使用和用戶相同的語言**"
        return system

    async def connect_mcp_servers(self) -> None:
        """
        连接你已启动的 FastMCP servers（你配置里 path="/"）。
        """
        await self.mcp.connect(name="timeemi", url="http://127.0.0.1:4200/")
        await self.mcp.connect(name="vision", url="http://127.0.0.1:4201/")

    async def close(self) -> None:
        await self.mcp.close()

    async def _execute_tool_call(
        self,
        tool_call: ToolCallLike,
        *,
        user_input: str,
        tool_output_as_user_prompt: bool = True,
    ) -> tuple[ToolMessage, list[dict[str, object]], ToolTraceItem]:
        """
        执行单个 tool_call（强类型校验 + trace）。

        返回：
        - ToolMessage：回填给 Tool Model
        - extra_msgs：作为下一轮 Tool Model 的额外 user messages（用于链式）
        - ToolTraceItem：结构化摘要（给 Chat Model）
        """
        full_name = tool_call.function.name

        # 1) args 强校验
        parsed = ToolRegistry.parse_args(full_name, tool_call.function.arguments)
        args_dict = parsed.args_model.model_dump(exclude_none=True)

        # 2) 调工具
        try:
            result_obj = await self.mcp.call_tool(full_name=full_name, args=args_dict)
            result_model = ToolRegistry.parse_result(full_name, result_obj)
            tool_text = ToolRegistry.tool_content_for_tool_model(full_name, result_model)

            tool_msg = ToolMessage(content=tool_text, tool_call_id=tool_call.id)
            trace = ToolRegistry.trace_item(parsed, result_model, ok=True, error=None)

        except Exception as e:
            # 不让异常打断 tool loop：记录错误，tool_msg 回填错误文本
            err = f"{type(e).__name__}: {e}"
            tool_msg = ToolMessage(content=err, tool_call_id=tool_call.id)
            trace = ToolTraceItem(
                server=parsed.server,
                name=parsed.name,
                args=args_dict,
                raw_result={},
                ok=False,
                error=err,
            )

        # 3) 链式 extra prompt（可选）
        extra_msgs: list[dict[str, object]] = []
        if tool_output_as_user_prompt and trace.ok:
            # 只对你已知工具做 prompt（扩展点：你以后可以加 vision 等）
            if parsed.full_name == "timeemi__get_date_and_time":
                # 这里传 raw datetime 给 server prompt 模板（让 Tool Model/Chat Model 自己口语化）
                dt = trace.raw_result.get("datetime")
                if isinstance(dt, str):
                    pr = await self.mcp.get_prompt(
                        full_name=parsed.full_name,
                        prompt_name="convert_time_readable",
                        args={"time_str": dt},
                    )
                    extra_msgs.append({"role": "user", "content": prompt_result_to_text(pr)})

            if parsed.full_name == "timeemi__roll_dice":
                nums = trace.raw_result.get("numbers")
                if isinstance(nums, list) and all(isinstance(x, int) for x in nums): # type: ignore
                    pr = await self.mcp.get_prompt(
                        full_name=parsed.full_name,
                        prompt_name="convert_list_int_readable",
                        args={"numbers": nums},
                    )
                    extra_msgs.append({"role": "user", "content": prompt_result_to_text(pr)})

        return tool_msg, extra_msgs, trace

    async def run_tool_loop(
        self,
        *,
        system_prompt: str,
        user_input: str,
        available_tools: list[dict[str, object]],
        max_steps: int = 6,
        max_parallel_tools: int = 6,
        debug: bool = True,
    ) -> tuple[list[dict[str, object]], list[ToolTraceItem]]:
        """
        Tool Model：非流式 + 支持并行/链式。

        返回：
        1) tool_loop_messages：完整轨迹（调试用）
        2) tool_trace：结构化摘要（给 Chat Model）
        """
        tool_loop_messages: list[dict[str, object]] = [
            OpenAIMessage(role="system", content=system_prompt).model_dump(exclude_none=True),
            OpenAIMessage(role="user", content=user_input).model_dump(exclude_none=True),
        ]
        tool_trace: list[ToolTraceItem] = []

        for step in range(max_steps):
            # Tool Model（非流式）
            resp = await call_with_short_retry( # type: ignore
                lambda: self.tool_client.chat.completions.create( # type: ignore
                    model=self.tool_model_name,
                    messages=tool_loop_messages, # type: ignore
                    tools=available_tools, # type: ignore
                    tool_choice="auto",
                    stream=False,
                ),
                max_retries=2,
            )

            assistant_msg = resp.choices[0].message # type: ignore
            tool_loop_messages.append(dump_openai_msg(assistant_msg)) # type: ignore

            tool_calls = getattr(assistant_msg, "tool_calls", None) # type: ignore
            if debug:
                names = [tc.function.name for tc in (tool_calls or [])] # type: ignore
                logger.info(f"[ToolLoop step={step}] tool_calls={names}")

            if not tool_calls:
                break

            # 同一轮并行执行（最多 max_parallel_tools 个）
            tool_calls = list(tool_calls)[:max_parallel_tools]
            results = await asyncio.gather(
                *[self._execute_tool_call(tc, user_input=user_input) for tc in tool_calls]
            )

            for tool_msg, extra_msgs, trace in results:
                tool_loop_messages.append(tool_msg.model_dump(exclude_none=True))
                tool_trace.append(trace)
                tool_loop_messages.extend(extra_msgs)

        return tool_loop_messages, tool_trace

    async def stream_chat_answer(
        self,
        *,
        system_prompt: str,
        user_input: str,
        tool_trace: list[ToolTraceItem],
    ):
        """
        Chat Model：流式输出最终回复（不做工具调用）。

        关键点：
        - 口语化/TTS 友好由 Chat Model 完成
        - 我们只提供结构化 trace，避免在 client 侧硬编码口语化逻辑
        """
        trace_dump = [t.model_dump(exclude_none=True) for t in tool_trace]
        tool_summary = json.dumps(trace_dump, ensure_ascii=False, indent=2) if trace_dump else "[]"

        messages: list[dict[str, object]] = [
            OpenAIMessage(role="system", content=system_prompt).model_dump(exclude_none=True),
            OpenAIMessage(
                role="system",
                content=(
                    "你已经通过工具拿到结构化结果（JSON）。"
                    "请基于这些结果用自然口语回答，并让输出适合 TTS 朗读（避免太“机器格式”）。\n\n"
                    f"工具结果摘要：\n{tool_summary}"
                ),
            ).model_dump(exclude_none=True),
            OpenAIMessage(role="user", content=user_input).model_dump(exclude_none=True),
        ]

        stream = await call_with_short_retry( # type: ignore
            lambda: self.chat_client.chat.completions.create( # type: ignore
                model=self.chat_model_name, # type: ignore
                messages=messages, # type: ignore
                stream=True,
            ),
            max_retries=2,
        )

        async for chunk in stream: # type: ignore
            delta = chunk.choices[0].delta # type: ignore
            content = getattr(delta, "content", None) # type: ignore
            if content:
                yield content

    async def chat_stream(self, user_input: str, *, debug: bool = True):
        system_prompt = self._load_system_prompt()
        available_tools = await self.mcp.list_tools_openai_schema()

        _, tool_trace = await self.run_tool_loop(
            system_prompt=system_prompt,
            user_input=user_input,
            available_tools=available_tools,
            debug=debug,
        )

        if debug:
            logger.info("[ToolTrace]")
            for t in tool_trace:
                logger.info(f"  - {t.server}::{t.name} args={t.args} ok={t.ok} result={t.raw_result} error={t.error}")

        async for tok in self.stream_chat_answer(system_prompt=system_prompt, user_input=user_input, tool_trace=tool_trace):
            yield tok


# =============================================================================
# 9) main：你的 5 个示例
# =============================================================================
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

        await run("昨天几号？")
        await run("今、何時ですか？")
        await run("我晚上九点就后就该去打游戏了，现在几点？")
        await run("帮我随便roll三个点数")
        await run("你今天真可爱")

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
