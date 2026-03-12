from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lab.agent.agents.memory_agent import MemoryAgent
from lab.agent.core import AgentCore
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
    from lab.agent.storage import ConversationStorage
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
    async def create_core_with_profile(
        lab_setting: XnneHangLabSettings,
        profile_path: Path,
        storage: ConversationStorage,
        tool_system_prompt: str = "",
        vision_system_prompt: str = "",
        workspace_root: Path | None = None,
    ) -> AgentCore:
        """基于 Profile 构造 AgentCore。

        Args:
            lab_setting: 全局实验室配置。
            profile_path: Profile 配置文件路径。
            storage: 会话存储实现。
            tool_system_prompt: 可选的工具系统提示词。
            vision_system_prompt: 可选的视觉系统提示词。
            workspace_root: 工作区根目录。

        Returns:
            构造完成的 AgentCore 实例。
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

        ws_root = workspace_root or Path.cwd()
        profile = Profile.from_toml(profile_path)
        agent_context = AgentContext(workspace_root=ws_root)

        plugin_loader = PluginLoader()
        tool_plugins, skill_descriptors = await plugin_loader.load_many(
            profile.plugins.enabled,
            profile_overrides=profile.plugins.overrides,
            ctx=agent_context,
        )

        tool_manager = build_default_tool_manager(ws_root)
        for tool_plugin in tool_plugins:
            for builtin_tool in tool_plugin.get_tools():
                tool_manager.register_builtin(builtin_tool)

        chat_system_prompt = SystemPromptBuilder(ws_root).build(
            persona_path=profile.prompt.persona,
            format_path=profile.prompt.format,
            skills=skill_descriptors,
            tool_manager=tool_manager,
        )

        core = AgentCore(
            chat_llm=chat_llm_interface,
            tool_llm=tool_llm_interface,
            vision_llm=vision_llm_interface,
            tool_manager=tool_manager,
            agent_context=agent_context,
            context_injector=ContextInjector(profile.context),
            storage=storage,
            chat_system_prompt=chat_system_prompt,
            tool_system_prompt=tool_system_prompt,
            vision_system_prompt=vision_system_prompt,
            enable_tool=lab_setting.agent.enable_tool,
            max_vision_concurrency=lab_setting.agent.max_vision_concurrency,
            require_detailed=lab_setting.agent.require_detailed,
        )
        core.chat_supports_vision = lab_setting.agent.chat_model.support_vision
        return core

    @staticmethod
    async def create_agent(
        lab_setting: XnneHangLabSettings,
        live2d_model: Live2dModel | None = None,
        tts_preprocessor_config: TTSPreprocessorConfig | None = None,
        workspace_root: Path | None = None,
    ) -> AgentInterface:
        """基于 lab_setting 构造 MemoryAgent（AgentCore 模式）。

        从 lab_setting.agent.memory_agent_profile 读取 Profile 路径，
        构建 AgentCore，再包装为 MemoryAgent。

        Args:
            lab_setting: 全局实验室配置。
            live2d_model: Live2D 模型实例。
            tts_preprocessor_config: TTS 预处理配置。
            workspace_root: 工作区根目录，默认为当前目录。

        Returns:
            构造完成的 MemoryAgent 实例。
        """
        from lab.agent.agents.memory_agent.memory_store import MemoryStore
        from lab.agent.storage import MemoryStoreAdapter

        ws_root = workspace_root or Path.cwd()

        profile_path_str = lab_setting.agent.memory_agent_profile
        if not profile_path_str:
            raise ValueError(
                "lab_setting.agent.memory_agent_profile 未配置，"
                '请在 lab.toml 的 [agent] 下设置 memory_agent_profile = "profiles/xxx.toml"'
            )
        profile_path = Path(profile_path_str)
        if not profile_path.is_absolute():
            profile_path = ws_root / profile_path_str
        if not profile_path.exists():
            raise FileNotFoundError(f"memory_agent_profile not found: {profile_path}")

        memory_store = MemoryStore()
        storage = MemoryStoreAdapter(memory_store)

        core = await AgentFactory.create_core_with_profile(
            lab_setting=lab_setting,
            profile_path=profile_path,
            storage=storage,
            workspace_root=ws_root,
        )

        agent = MemoryAgent(
            lab_settings=lab_setting,
            core=core,
            live2d_model=live2d_model,  # type: ignore[arg-type]
            tts_preprocessor_config=tts_preprocessor_config,  # type: ignore[arg-type]
            faster_first_response=lab_setting.agent.faster_first_response,
            segment_method=lab_setting.agent.segment_method,
            interrupt_method=lab_setting.agent.interrupt_method,
        )
        # 让 MemoryAgent 和 AgentCore 共用同一个 MemoryStore
        agent.memory = memory_store
        return agent
