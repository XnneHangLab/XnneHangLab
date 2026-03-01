"""memory_bench.mem0 — Patched mem0 Memory factory.

This module wraps ``mem0.Memory`` with monkey-patches to fix two known bugs
when running mem0 against non-OpenAI compatible backends (e.g. NewAPI):

Patch 1 — ``body.store`` unsupported (wrong_api_format)
--------------------------------------------------------
mem0's OpenAI LLM backend unconditionally injects ``store=True`` into every
chat-completion request.  This is an OpenAI-specific stored-completions
feature; third-party OpenAI-compatible APIs (NewAPI, vLLM, etc.) reject it
with HTTP 422::

    body.store: property 'body.store' is unsupported
    code: wrong_api_format

Fix: monkey-patch ``OpenAILLM.generate_response`` to skip the ``store``
injection block entirely.

Patch 2 — ``vector_store.update(vector=None, ...)`` ValidationError
--------------------------------------------------------------------
When mem0 processes a NONE-event (no new memory to add), it still calls
``vector_store.update(vector_id=…, vector=None, payload=…)`` to refresh
session metadata.  Qdrant's ``PointStruct`` does not accept ``vector=None``,
raising a ``ValidationError``.

Fix: monkey-patch ``vector_store.update`` per-instance to use
``set_payload`` (or a read-modify-write) when ``vector`` is ``None``.

Usage
-----
Replace::

    from mem0 import Memory
    memory = Memory.from_config(config)
    # ... manual vector_store patch ...

With::

    from memory_bench.mem0 import make_memory
    memory = make_memory(config)

The returned object is a standard ``mem0.Memory`` instance — both patches are
transparent to callers.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patch 1: strip `store` param for non-OpenAI backends
# Applied eagerly at import time (class-level, affects all instances).
# ---------------------------------------------------------------------------


def _patch_openai_llm_store() -> None:
    """Remove ``store`` injection from ``mem0.llms.openai.OpenAILLM``.

    mem0 hardcodes ``openai_specific_generation_params = ["store"]`` and
    passes it to every completion request.  Third-party OpenAI-compatible
    backends (NewAPI, vLLM, …) reject it with HTTP 422 wrong_api_format.
    """
    try:
        from mem0.llms.openai import OpenAILLM  # type: ignore[import-untyped]
    except ImportError:
        log.debug("mem0.llms.openai not available; skipping store patch")
        return

    def _new_generate_response(
        self: Any,
        messages: list[dict[str, str]],
        response_format: Any = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> Any:
        import json as _json
        import logging as _logging

        params = self._get_supported_params(messages=messages, **kwargs)
        params.update({
            "model": self.config.model,
            "messages": messages,
        })

        if os.getenv("OPENROUTER_API_KEY"):
            openrouter_params: dict[str, Any] = {}
            if self.config.models:
                openrouter_params["models"] = self.config.models
                openrouter_params["route"] = self.config.route
                params.pop("model")
            if self.config.site_url and self.config.app_name:
                openrouter_params["extra_headers"] = {
                    "HTTP-Referer": self.config.site_url,
                    "X-Title": self.config.app_name,
                }
            params.update(**openrouter_params)
        # NOTE: Intentionally skip the `store` injection block present in
        # upstream mem0.  `store` is an OpenAI-only stored-completions feature;
        # third-party backends return HTTP 422 wrong_api_format when it is sent.

        if response_format:
            params["response_format"] = response_format
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        response = self.client.chat.completions.create(**params)
        parsed_response = self._parse_response(response, tools)
        if self.config.response_callback:
            try:
                self.config.response_callback(self, response, params)
            except Exception as e:
                _logging.error("Error due to callback: %s", e)
        return parsed_response

    OpenAILLM.generate_response = _new_generate_response  # type: ignore[method-assign]
    log.debug("mem0 OpenAILLM.generate_response patched: `store` param removed")


# ---------------------------------------------------------------------------
# Patch 2: vector_store.update(vector=None) fix
# Applied per-instance after Memory.from_config().
# ---------------------------------------------------------------------------


def _patch_vector_store_update(memory: Any) -> None:
    """Patch ``memory.vector_store.update`` to handle ``vector=None``.

    When mem0 processes a NONE event it calls update with ``vector=None``,
    which Qdrant rejects.  We redirect to ``set_payload`` instead.
    """
    vector_store = getattr(memory, "vector_store", None)
    original_update = getattr(vector_store, "update", None)
    if not callable(original_update):
        return

    def _patched_update(
        vector_id: str,
        vector: Any = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if vector is None:
            client = getattr(vector_store, "client", None)
            if client is not None and hasattr(client, "set_payload"):
                collection_name = getattr(memory, "collection_name", None) or getattr(
                    vector_store, "collection_name", None
                )
                if collection_name:
                    client.set_payload(
                        collection_name=collection_name,
                        payload=payload or {},
                        points=[vector_id],
                    )
                    return

            # Fallback: read existing vector, then rewrite
            existing = None
            get_func = getattr(vector_store, "get", None)
            if callable(get_func):
                try:
                    existing = get_func(vector_id=vector_id)
                except TypeError:
                    existing = get_func(vector_id)

            existing_vector = getattr(existing, "vector", None)
            if existing_vector is not None:
                original_update(vector_id=vector_id, vector=existing_vector, payload=payload)
                return

            log.warning(
                "skip vector_store.update for %s: vector=None and no fallback available",
                vector_id,
            )
            return

        original_update(vector_id=vector_id, vector=vector, payload=payload)

    vector_store.update = _patched_update
    log.debug("mem0 vector_store.update patched: vector=None handled")


# Apply Patch 1 eagerly at import time so all subsequently created instances
# share the fixed behaviour automatically.
_patch_openai_llm_store()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_memory(config: dict[str, Any]) -> Any:
    """Create a fully-patched ``mem0.Memory`` instance from *config*.

    Both patches are applied automatically:

    * Patch 1 (``store`` param) is already in effect at import time.
    * Patch 2 (``vector=None``) is applied per-instance here.

    Replace::

        from mem0 import Memory
        memory = Memory.from_config(config)
        # ... manual vector_store patch boilerplate ...

    With::

        from memory_bench.mem0 import make_memory
        memory = make_memory(config)

    Args:
        config: mem0 configuration dict, same as ``Memory.from_config(config)``.

    Returns:
        A patched ``mem0.Memory`` instance.

    Raises:
        ImportError: if ``mem0`` is not installed.
        Exception: propagates any error from ``Memory.from_config``.
    """
    try:
        from mem0 import Memory as _Memory  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "mem0 is not installed. Install the memory_bench dependency group first, "
            "e.g. `uv sync --group memory_bench`."
        ) from exc

    memory = _Memory.from_config(config)
    _patch_vector_store_update(memory)
    return memory
