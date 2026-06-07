from __future__ import annotations

from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM

"""LLM factory (OpenAI-compatible only).

You said you only keep OpenAI now, so the factory no longer branches by provider.
It returns `AsyncLLM` directly (no extra stateless interface layer).
"""


class LLMFactory:
    @staticmethod
    def create_llm(*, model: str, base_url: str, llm_api_key: str) -> AsyncLLM:
        return AsyncLLM(
            model=model,
            base_url=base_url,
            llm_api_key=llm_api_key,
        )
