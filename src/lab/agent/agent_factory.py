from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lab.agent.agents.memory_agent import MemoryAgent
from lab.agent.stateless_llm_factory import LLMFactory
from lab.plugin.loader import PluginLoader
from lab.profile.context_injector import ContextInjector
from lab.profile.schema import Profile
from lab.profile.system_prompt_builder import SystemPromptBuilder
from lab.tools import (
    AgentContext,
    EditFileTool,
    GetDatetimeTool,
    ListDirTool,
    ReadFileTool,
    ToolManager,
    WriteFileTool,
)

if TYPE_CHECKING:
    from lab.agent.agents.agent_interface import AgentInterface
    from lab.config_manager import XnneHangLabSettings
    from lab.config_manager.vtuber import TTSPreprocessorConfig
    from lab.live2d_model import Live2dModel


def build_default_tool_manager(workspace_root: Path) -> ToolManager:
    """构建并注册默认内置工具集的 ToolManager。

    工具集：get_datetime / read_file / write_file / edit_file / list_dir
    workspace_root 作为文件操作的安全边界传入 AgentContext。
    """
    tm = ToolManager()
    tm.register_builtin(GetDatetimeTool())
    tm.register_builtin(ReadFileTool())
    tm.register_builtin(WriteFileTool())
    tm.register_builtin(EditFileTool())
    tm.register_builtin(ListDirTool())
    return tm


class AgentFactory:
    @staticmethod
    def create_agent(
        lab_setting: XnneHangLabSettings,
        chat_system_prompt: str,
        tool_system_prompt: str = "",
        vision_system_prompt: str = "",
        live2d_model: Live2dModel | None = None,
        tts_preprocessor_config: TTSPreprocessorConfig | None = None,
        workspace_root: Path | None = None,
    ) -> AgentInterface:
        """Create an agent based on configuration (OpenAI only, dual-model ready).

        tool_system_prompt 现在是可选参数：
        - 传入时直接使用（向后兼容）
        - 不传时由 ToolManager.build_system_prompt() 自动生成

        workspace_root 用于 AgentContext 的文件操作安全边界：
        - 传入时使用指定路径
        - 不传时默认使用当前工作目录
        """
        tool_model = lab_setting.agent.tool_model
        chat_model = lab_setting.agent.chat_model
        vision_model = lab_setting.agent.vision_model

        tool_llm = getattr(lab_setting.agent.llm, tool_model.llm_provider)
        chat_llm = getattr(lab_setting.agent.llm, chat_model.llm_provider)
        vision_llm = getattr(lab_setting.agent.llm, vision_model.llm_provider)

        chat_llm_interface = LLMFactory.create_llm(
            model=chat_model.llm_model_name,
            base_url=chat_llm.llm_base_url,
            llm_api_key=chat_llm.llm_api_key,
        )

        tool_llm_interface = LLMFactory.create_llm(
            model=tool_model.llm_model_name,
            base_url=tool_llm.llm_base_url,
            llm_api_key=tool_llm.llm_api_key,
        )

        vision_llm_interface = LLMFactory.create_llm(
            model=vision_model.llm_model_name,
            base_url=vision_llm.llm_base_url,
            llm_api_key=vision_llm.llm_api_key,
        )

        # 构建 ToolManager + AgentContext
        ws_root = workspace_root or Path.cwd()
        tool_manager = build_default_tool_manager(ws_root)
        agent_context = AgentContext(workspace_root=ws_root)

        return MemoryAgent(
            lab_settings=lab_setting,
            chat_llm=chat_llm_interface,
            tool_llm=tool_llm_interface,
            vision_llm=vision_llm_interface,
            chat_system_prompt=chat_system_prompt,
            tool_system_prompt=tool_system_prompt,  # 空串时由 MemoryAgent 自动生成
            vision_system_prompt=vision_system_prompt,
            enable_tool=lab_setting.agent.enable_tool,
            live2d_model=live2d_model,  # type: ignore[arg-type]
            tts_preprocessor_config=tts_preprocessor_config,  # type: ignore[arg-type]
            faster_first_response=lab_setting.agent.faster_first_response,
            segment_method=lab_setting.agent.segment_method,
            interrupt_method=lab_setting.agent.interrupt_method,
            tool_manager=tool_manager,
            agent_context=agent_context,
        )

    @staticmethod
    async def create_agent_with_profile(
        lab_setting: XnneHangLabSettings,
        profile_path: Path,
        tool_system_prompt: str = "",
        vision_system_prompt: str = "",
        live2d_model: Live2dModel | None = None,
        tts_preprocessor_config: TTSPreprocessorConfig | None = None,
        workspace_root: Path | None = None,
    ) -> AgentInterface:
        """基于 Profile 创建 Agent。

        Args:
            lab_setting: 全局实验室配置。
            profile_path: Profile 文件路径。
            tool_system_prompt: 工具模型系统提示词。
            vision_system_prompt: 视觉模型系统提示词。
            live2d_model: Live2D 模型实例。
            tts_preprocessor_config: TTS 预处理配置。
            workspace_root: 工作区根目录，未传入时优先使用 lab_setting.root.root_dir。

        Returns:
            AgentInterface: 已按 Profile 完成插件、Prompt 与 ContextInjector 装配的 Agent。
        """
        tool_model = lab_setting.agent.tool_model
        chat_model = lab_setting.agent.chat_model
        vision_model = lab_setting.agent.vision_model

        tool_llm = getattr(lab_setting.agent.llm, tool_model.llm_provider)
        chat_llm = getattr(lab_setting.agent.llm, chat_model.llm_provider)
        vision_llm = getattr(lab_setting.agent.llm, vision_model.llm_provider)

        chat_llm_interface = LLMFactory.create_llm(
            model=chat_model.llm_model_name,
            base_url=chat_llm.llm_base_url,
            llm_api_key=chat_llm.llm_api_key,
        )

        tool_llm_interface = LLMFactory.create_llm(
            model=tool_model.llm_model_name,
            base_url=tool_llm.llm_base_url,
            llm_api_key=tool_llm.llm_api_key,
        )

        vision_llm_interface = LLMFactory.create_llm(
            model=vision_model.llm_model_name,
            base_url=vision_llm.llm_base_url,
            llm_api_key=vision_llm.llm_api_key,
        )

        ws_root = workspace_root or Path(lab_setting.root.root_dir)
        agent_context = AgentContext(workspace_root=ws_root)
        tool_manager = build_default_tool_manager(ws_root)

        profile = Profile.from_toml(profile_path)

        plugin_loader = PluginLoader()
        tool_plugins, skill_descriptors = await plugin_loader.load_many(
            profile.plugins.enabled,
            profile_overrides=profile.plugins.overrides,
            ctx=agent_context,
        )
        for tool_plugin in tool_plugins:
            for builtin_tool in tool_plugin.get_tools():
                tool_manager.register_builtin(builtin_tool)

        chat_system_prompt = SystemPromptBuilder(ws_root).build(
            persona_path=profile.prompt.persona,
            format_path=profile.prompt.format,
            skills=skill_descriptors,
            tool_manager=tool_manager,
        )

        return MemoryAgent(
            lab_settings=lab_setting,
            chat_llm=chat_llm_interface,
            tool_llm=tool_llm_interface,
            vision_llm=vision_llm_interface,
            chat_system_prompt=chat_system_prompt,
            tool_system_prompt=tool_system_prompt,
            vision_system_prompt=vision_system_prompt,
            enable_tool=lab_setting.agent.enable_tool,
            live2d_model=live2d_model,  # type: ignore[arg-type]
            tts_preprocessor_config=tts_preprocessor_config,  # type: ignore[arg-type]
            faster_first_response=lab_setting.agent.faster_first_response,
            segment_method=lab_setting.agent.segment_method,
            interrupt_method=lab_setting.agent.interrupt_method,
            tool_manager=tool_manager,
            agent_context=agent_context,
            context_injector=ContextInjector(profile.context),
        )
