from __future__ import annotations


class ContextInjector:
    """Build tagged context blocks for user prompt injection."""

    def build_context_prompt(
        self,
        *,
        memory_context: str | None = None,
    ) -> str | None:
        if not memory_context:
            return None
        return f"[memory context]\n{memory_context}\n[/memory context]"
