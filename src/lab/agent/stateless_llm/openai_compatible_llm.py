"""OpenAI-compatible async LLM wrapper (no extra interface layer).

- chat_completion: stream tokens for final chat output
- tool_completion: non-stream call with tools for MCP tool loop

This module intentionally does NOT depend on any MemoryManager abstraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from openai import APIConnectionError, APIError, AsyncOpenAI, AsyncStream, RateLimitError

from lab.mcp.util import call_with_short_retry  # type: ignore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from openai.types.chat import ChatCompletion, ChatCompletionChunk


class AsyncLLM:
    """A thin wrapper around `AsyncOpenAI` (OpenAI-compatible endpoints)."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        llm_api_key: str,
        organization_id: str = "z",
        project_id: str = "z",
        temperature: float = 1.0,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.client = AsyncOpenAI(
            base_url=base_url,
            organization=organization_id,
            project=project_id,
            api_key=llm_api_key,
        )
        logger.info(f"Initialized AsyncLLM: base_url={self.base_url}, model={self.model}")

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        *,
        stream_: bool = True,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Generate a chat completion.

        - When `stream_` is True, yields token chunks.
        - When `stream_` is False, yields a single full string.
        """
        origin_user_message = messages[-1]["content"] if messages else ""
        stream: AsyncStream[ChatCompletionChunk] | None = None

        try:
            messages_with_system = messages
            if system:
                messages_with_system = [{"role": "system", "content": system}, *messages]

            temp = self.temperature if temperature is None else temperature

            if stream_:
                stream = await self.client.chat.completions.create(  # type: ignore[return-value]
                    messages=messages_with_system,  # type: ignore[arg-type]
                    model=self.model,
                    stream=True,
                    temperature=temp,
                )

                if messages_with_system:
                    messages_with_system[-1]["content"] = origin_user_message

                async for chunk in stream:  # type: ignore[return-value]
                    delta = chunk.choices[0].delta  # type: ignore[attr-defined]
                    if delta.content is None:  # type: ignore[union-attr]
                        delta.content = ""  # type: ignore[assignment]
                    yield delta.content  # type: ignore[misc]
            else:
                response = await self.client.chat.completions.create(  # type: ignore[return-value]
                    messages=messages_with_system,  # type: ignore[arg-type]
                    model=self.model,
                    stream=False,
                    temperature=temp,
                )

                if messages_with_system:
                    messages_with_system[-1]["content"] = origin_user_message

                assistant_msg = response.choices[0].message  # type: ignore[attr-defined]
                yield assistant_msg.content or ""  # type: ignore[misc]

        except APIConnectionError as e:
            logger.error(
                "Connection error calling chat endpoint. Check base_url/api_key and LLM backend reachability. "
                f"{e.__cause__}"
            )
            yield "Error calling the chat endpoint: Connection error. Failed to connect to the LLM API."

        except RateLimitError as e:
            logger.error(f"Rate limit exceeded: {e.response}")
            yield "Error calling the chat endpoint: Rate limit exceeded. Please try again later."

        except APIError as e:
            logger.error(f"LLM API error: {e}")
            logger.info(f"base_url={self.base_url} model={self.model} temperature={self.temperature}")
            yield "Error calling the chat endpoint: Error occurred while generating response."

        finally:
            if stream is not None:
                try:
                    await stream.close()  # type: ignore[union-attr]
                except Exception:
                    pass

    async def tool_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] = "auto",
        system: str | None = None,
        temperature: float | None = None,
    ) -> ChatCompletion:
        """Non-stream tool decision call (returns full response object)."""
        messages_with_system = messages
        if system:
            messages_with_system = [{"role": "system", "content": system}, *messages]

        temp = self.temperature if temperature is None else temperature

        return await call_with_short_retry(
            lambda: self.client.chat.completions.create(  # type: ignore[return-value]
                model=self.model,
                messages=messages_with_system,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
                tool_choice=tool_choice,  # type: ignore[arg-type]
                stream=False,
                temperature=temp,
            ),
            max_retries=2,
        )  # type: ignore[return-value]

    async def vision_completion_once(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        *,
        temperature: float | None = None,
    ) -> str:
        base_msgs = list(messages)
        messages_with_system = ([{"role": "system", "content": system}] + base_msgs) if system else base_msgs
        temp = self.temperature if temperature is None else temperature

        resp = await call_with_short_retry(  # type: ignore[assignment]
            lambda: self.client.chat.completions.create(  # type: ignore[return-value]
                model=self.model,
                messages=messages_with_system,  # type: ignore[arg-type]
                stream=False,
                temperature=temp,
            ),
            max_retries=2,
        )
        return (resp.choices[0].message.content or "").strip()  # type: ignore[misc]
