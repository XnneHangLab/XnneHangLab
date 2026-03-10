"""Memory Proxy Router — 透明代理端点

职责：接收标准 OpenAI Chat Completions 请求 → 注入 mem0 记忆 → 完整透传给上游 LLM
     → 异步写回 mem0 + 图谱管线。

设计原则：
- 对调用方完全透明：换个 base_url 即可接入，不感知记忆层的存在
- stream=true/false 均支持，SSE chunks 原样透传
- tool_call / tool 消息完整透传，不过滤
- 写回时只写 user + assistant 轮次，工具调用中间步骤不写入 mem0
- 标准 OpenAI error format 透传，不包装成 502
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from memory_bench.scripts.bench_logger import logger
from memory_bench.server.router import (
    format_memories,
    memory_and_graph_background,
    search_memories,
    state,
    verify_api_key,
)

# ---------------------------------------------------------------------------
# Pydantic models（宽松版，允许 extra，兼容 OpenAI 所有字段）
# ---------------------------------------------------------------------------

_MEMORY_INJECTION_TEMPLATE = (
    "\n\n## Recalled Memories\n"
    "The following memories were recalled from previous conversations and may be relevant:\n\n"
    "{memories}\n\n"
    "---\n"
    'Use these memories naturally in your response when relevant. '
    'Do not mention that you "recalled" or "retrieved" them.'
)


class _AnyMessage(BaseModel):
    """宽松的 message 模型：保留所有字段原样透传。"""

    role: str
    content: str | list[Any] | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[Any] | None = None

    model_config = {"extra": "allow"}


class _ProxyRequest(BaseModel):
    """接收来自客户端的 OpenAI 格式请求（完整字段保留）。"""

    model: str = ""
    messages: list[_AnyMessage]
    stream: bool = False

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# 透传辅助
# ---------------------------------------------------------------------------


def _messages_to_dicts(messages: list[_AnyMessage]) -> list[dict[str, Any]]:
    """把 _AnyMessage 列表序列化为 OpenAI API 接受的 dict 列表。

    注意：保留 tool_calls / tool_call_id / content=null 等字段，不做任何过滤。
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        d: dict[str, Any] = {"role": m.role}
        if m.content is not None:
            d["content"] = m.content
        if m.name is not None:
            d["name"] = m.name
        if m.tool_call_id is not None:
            d["tool_call_id"] = m.tool_call_id
        if m.tool_calls is not None:
            d["tool_calls"] = m.tool_calls
        # 保留 extra 字段（如 function_call 等）
        for k, v in (m.model_extra or {}).items():
            d[k] = v
        out.append(d)
    return out


def _inject_memories_any(messages: list[_AnyMessage], memories_text: str) -> list[_AnyMessage]:
    """把记忆注入 system message 末尾，保持其余 message 不变。"""
    if not memories_text:
        return messages
    injection = _MEMORY_INJECTION_TEMPLATE.format(memories=memories_text)
    result = list(messages)
    for i, msg in enumerate(result):
        if msg.role == "system":
            existing = msg.content if isinstance(msg.content, str) else ""
            result[i] = msg.model_copy(update={"content": existing + injection})
            return result
    result.insert(0, _AnyMessage(role="system", content=injection))
    return result


def _extract_last_user_text(messages: list[_AnyMessage]) -> str:
    """提取最后一条 user message 的文本内容。"""
    for m in reversed(messages):
        if m.role == "user":
            return m.content if isinstance(m.content, str) else ""
    return ""


def _should_writeback(assistant_msg: dict[str, Any]) -> tuple[bool, str]:
    """判断 assistant 消息是否应写回 mem0，以及提取文本内容。

    写回策略：只写真实回复（无 tool_calls）。
    """
    if assistant_msg.get("tool_calls"):
        return False, ""
    content = assistant_msg.get("content", "") or ""
    return bool(content), content if isinstance(content, str) else ""


# ---------------------------------------------------------------------------
# 上游 URL / headers
# ---------------------------------------------------------------------------


def _upstream_url(path: str) -> str:
    client = state.openai_client
    if client is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    # OpenAI SDK 会在 base_url 末尾自动追加 /v1/，需要剥掉再拼接，避免 double /v1/
    base = str(client.base_url).rstrip("/")
    base = base.removesuffix("/v1")
    return f"{base}/{path.lstrip('/')}"


def _upstream_headers() -> dict[str, str]:
    client = state.openai_client
    if client is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    api_key = client.api_key or ""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

proxy_router = APIRouter()


@proxy_router.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)], response_model=None)
async def proxy_chat_completions(raw_request: Request) -> StreamingResponse | JSONResponse:
    """透明代理：注入记忆后完整转发给上游 LLM，stream / non-stream 均支持。"""
    log = logger.bind(group="proxy")

    # 1. 读取原始 body
    try:
        raw_body: dict[str, Any] = await raw_request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    req = _ProxyRequest.model_validate(raw_body)

    # 2. 记忆召回（search_memories 是同步 IO，用线程池避免阻塞事件循环）
    latest_user_text = _extract_last_user_text(req.messages)
    memories: list[dict[str, Any]] = []
    if latest_user_text:
        loop = asyncio.get_event_loop()
        memories = await loop.run_in_executor(None, search_memories, latest_user_text)
        if memories:
            log.info("🔍 Found %d memories for query", len(memories))

    memories_text = format_memories(memories)
    augmented_messages = _inject_memories_any(req.messages, memories_text)

    # 3. 构造转发 body（extra 字段保留，messages 替换）
    forward_body: dict[str, Any] = dict(raw_body)
    forward_body["messages"] = _messages_to_dicts(augmented_messages)
    model = req.model or state.chat_model or ""
    if model:
        forward_body["model"] = model

    url = _upstream_url("v1/chat/completions")
    headers = _upstream_headers()
    log.info(f"🔀 Forwarding to: {url}")

    # 4. 透传
    if req.stream:
        return StreamingResponse(
            _stream_generator(forward_body, url, headers, req.messages, log),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await _non_stream_response(forward_body, url, headers, req.messages, log)


async def _non_stream_response(
    body: dict[str, Any],
    url: str,
    headers: dict[str, str],
    original_messages: list[_AnyMessage],
    log: Any,
) -> JSONResponse:
    """非流式：转发并直接返回上游响应 JSON。"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}") from exc

    if resp.status_code != 200:
        try:
            error_body: dict[str, Any] = resp.json()
        except Exception:
            error_body = {"error": {"message": resp.text, "type": "upstream_error"}}
        return JSONResponse(content=error_body, status_code=resp.status_code)

    try:
        resp_json: dict[str, Any] = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream returned invalid JSON: {exc}") from exc

    # 写回判断
    choices = resp_json.get("choices", [])
    if choices:
        assistant_msg: dict[str, Any] = choices[0].get("message", {})
        should_write, assistant_content = _should_writeback(assistant_msg)
        latest_user = _extract_last_user_text(original_messages)
        if should_write and latest_user:
            log.info("💾 Queued memory write-back (non-stream)")
            asyncio.create_task(memory_and_graph_background(latest_user, assistant_content))

    return JSONResponse(content=resp_json)


async def _stream_generator(
    body: dict[str, Any],
    url: str,
    headers: dict[str, str],
    original_messages: list[_AnyMessage],
    log: Any,
) -> AsyncGenerator[str, None]:
    """SSE 流式生成器：原样透传上游 chunks，结束后异步写回。"""
    assistant_chunks: list[str] = []
    has_tool_calls = False

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    try:
                        error_json = json.loads(error_text)
                    except Exception:
                        error_json = {"error": {"message": error_text.decode(), "type": "upstream_error"}}
                    yield f"data: {json.dumps(error_json)}\n\n"
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        yield "\n"
                        continue

                    # SSE 每条 data: 行需要以 \n\n 结尾，OpenAI SDK 才能正确解析
                    yield line + "\n\n"

                    # 解析 data: 行，用于写回判断
                    if line.startswith("data: "):
                        chunk_text = line[6:].strip()
                        if chunk_text == "[DONE]":
                            continue
                        try:
                            chunk: dict[str, Any] = json.loads(chunk_text)
                            delta: dict[str, Any] = chunk.get("choices", [{}])[0].get("delta", {})
                            if delta.get("tool_calls"):
                                has_tool_calls = True
                            content = delta.get("content")
                            if content:
                                assistant_chunks.append(content)
                        except Exception:
                            pass

        except httpx.RequestError as exc:
            err = json.dumps({"error": {"message": str(exc), "type": "upstream_error"}})
            yield f"data: {err}\n\n"
            return

    yield "data: [DONE]\n\n"

    # 流结束后写回
    if not has_tool_calls and assistant_chunks:
        assistant_content = "".join(assistant_chunks)
        latest_user = _extract_last_user_text(original_messages)
        if latest_user and assistant_content:
            log.info("💾 Queued memory write-back (stream)")
            asyncio.create_task(memory_and_graph_background(latest_user, assistant_content))


@proxy_router.get("/v1/models", dependencies=[Depends(verify_api_key)], response_model=None)
async def proxy_list_models() -> JSONResponse:
    """透传上游 /v1/models，或返回本地 fallback。"""
    try:
        url = _upstream_url("v1/models")
        headers = _upstream_headers()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            resp_json: dict[str, Any] = resp.json()
            return JSONResponse(content=resp_json)
    except Exception:
        pass
    return JSONResponse(
        content={
            "object": "list",
            "data": [{"id": state.chat_model, "object": "model", "owned_by": "memory-proxy"}],
        }
    )


@proxy_router.get("/health", response_model=None)
async def proxy_health() -> JSONResponse:
    """健康检查。"""
    return JSONResponse(
        content={
            "status": "ok",
            "mem0_ready": state.mem0 is not None,
            "llm_ready": state.openai_client is not None,
            "model": state.chat_model,
            "graph_pipeline_enabled": state.graph_pipeline_enabled,
            "stream_support": True,
        }
    )
