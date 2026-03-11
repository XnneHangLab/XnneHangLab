from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab.profile.schema import ContextConfig


class ContextInjector:
    """
    负责生成注入 user prompt 的 context 标签块。
    Context 不进 system prompt，每轮动态生成。
    """

    def __init__(self, config: ContextConfig) -> None:
        self._config = config

    def build_context_prompt(
        self,
        *,
        memory_context: str | None = None,
        diary_context: str | None = None,
        user_context: str | None = None,
    ) -> str | None:
        parts: list[str] = []
        if self._config.memory_search and memory_context:
            parts.append(f"[memory context]\n{memory_context}\n[/memory context]")
        if self._config.diary_summary and diary_context:
            parts.append(f"[diary context]\n{diary_context}\n[/diary context]")
        if self._config.user_context and user_context:
            parts.append(f"[user context]\n{user_context}\n[/user context]")
        return "\n\n".join(parts) if parts else None
