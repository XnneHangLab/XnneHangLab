from __future__ import annotations

from typing import TYPE_CHECKING

from lab.agent.agents.memory_agent import MemoryAgent
from lab.agent.stateless_llm_factory import LLMFactory

if TYPE_CHECKING:
    from lab.agent.agents.agent_interface import AgentInterface
    from lab.config_manager import XnneHangLabSettings
    from lab.config_manager.vtuber import TTSPreprocessorConfig
    from lab.live2d_model import Live2dModel


class AgentFactory:
    @staticmethod
    def create_agent(
        lab_setting: XnneHangLabSettings,
        system_prompt: str,
        live2d_model: Live2dModel,
        tts_preprocessor_config: TTSPreprocessorConfig,
    ) -> type[AgentInterface]:
        """Create an agent based on configuration (OpenAI only, dual-model ready).

        Note:
        - `enable_tool` is an explicit switch (defaults to False if not present in config).
        - We still create tool_llm so you can turn tools on/off at runtime without re-wiring.
        """
        tool_model = lab_setting.agent.tool_model
        chat_model = lab_setting.agent.chat_model

        tool_llm = getattr(lab_setting.agent.llm, tool_model.llm_provider)
        chat_llm = getattr(lab_setting.agent.llm, chat_model.llm_provider)

        chat_llm = LLMFactory.create_llm(
            model=chat_model.llm_model_name,
            base_url=chat_llm.llm_base_url,
            llm_api_key=chat_llm.llm_api_key,
        )

        tool_llm = LLMFactory.create_llm(
            model=tool_model.llm_model_name,
            base_url=tool_llm.llm_base_url,
            llm_api_key=tool_llm.llm_api_key,
        )

        return MemoryAgent(  # type: ignore[call-arg]
            chat_llm=chat_llm,
            tool_llm=tool_llm,
            enable_tool=lab_setting.agent.enable_mcp,  # TODO 区分 enable_mcp 和 enable_tool, enable_mcp 是 enable_mcp 的超集
            system=system_prompt,
            live2d_model=live2d_model,
            tts_preprocessor_config=tts_preprocessor_config,
            faster_first_response=lab_setting.agent.faster_first_response,
            segment_method=lab_setting.agent.segment_method,
            interrupt_method=lab_setting.agent.interrupt_method,
        )
