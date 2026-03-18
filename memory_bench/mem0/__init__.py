"""memory_bench.mem0 — 帶有 Patch 的 mem0 Memory 工廠模塊。

本模塊對 ``mem0.Memory`` 進行 monkey-patch，修復在非 OpenAI 后端
（如 NewAPI、vLLM 等 OpenAI-compatible 服務）下的兩個已知 Bug：

Patch 1 — ``body.store`` 不支持（wrong_api_format）
-----------------------------------------------------
mem0 的 OpenAI LLM 后端會無條件向每個 chat completion 請求注入
``store=True`` 參數。這是 OpenAI 專屬的 stored-completions 功能，
第三方 OpenAI-compatible API 不支持該字段，會返回 HTTP 422::

    body.store: property 'body.store' is unsupported
    code: wrong_api_format

修復方案：monkey-patch ``OpenAILLM.generate_response``，跳過 ``store``
注入邏輯。此 patch 在 import 時自動生效（class-level，影響所有實例）。

Patch 2 — ``vector_store.update(vector=None, ...)`` ValidationError
--------------------------------------------------------------------
mem0 在處理 NONE 事件（無新記憶需要添加）時，仍會調用
``vector_store.update(vector_id=…, vector=None, payload=…)`` 以刷新
session metadata。Qdrant 的 ``PointStruct`` 不接受 ``vector=None``，
會拋出 ``ValidationError``。

修復方案：per-instance monkey-patch ``vector_store.update``，
當 ``vector`` 為 ``None`` 時改用 ``set_payload``（或 read-modify-write fallback）。

用法
----
替換原有寫法::

    from mem0 import Memory
    memory = Memory.from_config(config)
    # ... 手動 patch vector_store.update ...

改用::

    from memory_bench.mem0 import make_memory
    memory = make_memory(config)

返回的對象是標準 ``mem0.Memory`` 實例，兩個 patch 對調用方完全透明。
"""

from __future__ import annotations

import logging
import os
from typing import Any, cast

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patch 1: 移除 `store` 參數，兼容非 OpenAI 后端
# 在 import 時立即生效（class-level，影響所有實例）。
# ---------------------------------------------------------------------------


def _patch_openai_llm_store() -> None:
    """移除 ``mem0.llms.openai.OpenAILLM`` 中的 ``store`` 注入。

    mem0 硬編碼了 ``openai_specific_generation_params = ["store"]``，
    並將其注入到每個 completion 請求中。第三方 OpenAI-compatible 后端
    （NewAPI、vLLM 等）不支持此字段，返回 HTTP 422 wrong_api_format。
    """
    try:
        from mem0.llms.openai import OpenAILLM  # type: ignore[import-untyped]
    except ImportError:
        log.debug("mem0.llms.openai 不可用，跳過 store patch")
        return

    def _new_generate_response(
        self: Any,
        messages: list[dict[str, str]],
        response_format: Any = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> Any:
        import logging as _logging

        params = self._get_supported_params(messages=messages, **kwargs)
        params.update(
            {
                "model": self.config.model,
                "messages": messages,
            }
        )

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
        # 注意：故意跳過上游 mem0 中的 `store` 注入邏輯。
        # `store` 是 OpenAI 專屬的 stored-completions 功能，
        # 第三方后端收到此字段會返回 HTTP 422 wrong_api_format。

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
                _logging.error("callback 執行出錯：%s", e)
        return parsed_response

    OpenAILLM.generate_response = _new_generate_response  # type: ignore[method-assign]
    log.debug("已 patch mem0 OpenAILLM.generate_response：移除 `store` 參數")


# ---------------------------------------------------------------------------
# Patch 2: 修復 vector_store.update(vector=None) 問題
# per-instance 應用，在 Memory.from_config() 之後執行。
# ---------------------------------------------------------------------------


def _patch_vector_store_update(memory: Any) -> None:
    """Patch ``memory.vector_store.update``，處理 ``vector=None`` 的情況。

    mem0 在處理 NONE 事件時會傳入 ``vector=None``，Qdrant 不接受此值。
    改用 ``set_payload`` 僅更新 payload，或通過 read-modify-write 回退。
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

            # 回退方案：讀取現有 vector 後重新寫入
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
                "跳過 vector_store.update（%s）：vector=None 且無可用回退方案",
                vector_id,
            )
            return

        original_update(vector_id=vector_id, vector=vector, payload=payload)

    if vector_store is None:
        return
    vector_store.update = _patched_update  # type: ignore[reportAttributeAccessIssue]
    log.debug("已 patch mem0 vector_store.update：處理 vector=None 情況")


# import 時立即應用 Patch 1，后續創建的所有實例自動繼承修復。
_patch_openai_llm_store()


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def make_memory(config: dict[str, Any]) -> Any:
    """根據 *config* 創建帶有完整 patch 的 ``mem0.Memory`` 實例。

    兩個 patch 均自動應用：

    * Patch 1（``store`` 參數）：import 時已生效。
    * Patch 2（``vector=None``）：此函數內 per-instance 應用。

    替換原有寫法::

        from mem0 import Memory
        memory = Memory.from_config(config)
        # ... 手動 patch 樣板代碼 ...

    改用::

        from memory_bench.mem0 import make_memory
        memory = make_memory(config)

    參數：
        config: mem0 配置字典，與 ``Memory.from_config(config)`` 格式相同。

    返回：
        帶有 patch 的 ``mem0.Memory`` 實例。

    拋出：
        ImportError: mem0 未安裝時。
        Exception: ``Memory.from_config`` 拋出的任何異常。
    """
    try:
        from mem0 import Memory as imported_memory  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("mem0 未安裝。請先安裝 memory_bench 依賴組，例如：`uv sync --group memory_bench`。") from exc

    memory_cls = cast("type[Any]", imported_memory)
    memory = memory_cls.from_config(config)
    _patch_vector_store_update(memory)
    return memory
