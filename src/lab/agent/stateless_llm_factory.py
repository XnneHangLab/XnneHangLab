from __future__ import annotations

from typing import TYPE_CHECKING

from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM as OpenAICompatibleLLM

if TYPE_CHECKING:
    from lab.agent.stateless_llm.stateless_llm_interface import StatelessLLMInterface


class LLMFactory:
    @staticmethod
    def create_llm(
        model: str,
        base_url: str,
        llm_api_key: str,
    ) -> type[StatelessLLMInterface]:
        """Create an LLM based on the configuration.

        Args:
            llm_provider: The type of LLM to create
            **kwargs: Additional arguments
        """

        return OpenAICompatibleLLM(  # type: ignore[call-arg]
            model=model,
            base_url=base_url,
            llm_api_key=llm_api_key,
        )


# 使用工廠創建 LLM 實例
# llm_instance = LLMFactory.create_llm("ollama", **config_dict)
