from __future__ import annotations

from typing import TYPE_CHECKING

from lab.agent.agents.basic_memory_agent import BasicMemoryAgent
from lab.agent.stateless_llm_factory import LLMFactory as StatelessLLMFactory

if TYPE_CHECKING:
    from lab.agent.agents.agent_interface import AgentInterface
    from lab.config_manager import AgentSettings
    from lab.config_manager.vtuber import TTSPreprocessorConfig
    from lab.live2d_model import Live2dModel


class AgentFactory:
    @staticmethod
    def create_agent(
        agent_settings: AgentSettings,
        system_prompt: str,
        live2d_model: Live2dModel,
        tts_preprocessor_config: TTSPreprocessorConfig,
    ) -> type[AgentInterface]:
        """Create an agent based on the configuration.

        Args:
            conversation_agent_choice: The type of agent to create
            agent_settings: Settings for different types of agents
            llm_configs: Pool of LLM configurations
            system_prompt: The system prompt to use
            live2d_model: Live2D model instance for expression extraction
            tts_preprocessor_config: Configuration for TTS preprocessing
            **kwargs: Additional arguments
        """
        if agent_settings.llm_provider == "lingyi":
            llm = StatelessLLMFactory.create_llm(
                model=agent_settings.llm.lingyi.llm_model_name,
                base_url=agent_settings.llm.lingyi.llm_base_url,
                llm_api_key=agent_settings.llm.lingyi.llm_api_key,
            )
        elif agent_settings.llm_provider == "gemini":
            llm = StatelessLLMFactory.create_llm(
                model=agent_settings.llm.gemini.llm_model_name,
                base_url=agent_settings.llm.gemini.llm_base_url,
                llm_api_key=agent_settings.llm.gemini.llm_api_key,
            )
        elif agent_settings.llm_provider == "openai":
            llm = StatelessLLMFactory.create_llm(
                model=agent_settings.llm.openai.llm_model_name,
                base_url=agent_settings.llm.openai.llm_base_url,
                llm_api_key=agent_settings.llm.openai.llm_api_key,
            )
        elif agent_settings.llm_provider == "oaipro":
            llm = StatelessLLMFactory.create_llm(
                model=agent_settings.llm.oaipro.llm_model_name,
                base_url=agent_settings.llm.oaipro.llm_base_url,
                llm_api_key=agent_settings.llm.oaipro.llm_api_key,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {agent_settings.llm_provider}")

        # Create the agent with the LLM and live2d_model
        return BasicMemoryAgent(  # type: ignore[call-arg]
            llm=llm,  # type: ignore[arg-type]s
            system=system_prompt,
            live2d_model=live2d_model,
            tts_preprocessor_config=tts_preprocessor_config,
            faster_first_response=agent_settings.faster_first_response,
            segment_method=agent_settings.segment_method,
            interrupt_method=agent_settings.interrupt_method,
        )
