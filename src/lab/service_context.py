from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from lab.agent.agent_factory import AgentFactory
from lab.api.logic.translate import TranslateEngineRouter
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.config_manager.vtuber import CharacterSettings, TTSPreprocessorConfig as VTuberTTSConfig
from lab.live2d_model import Live2dModel
from lab.profile.schema import Profile

if TYPE_CHECKING:
    from fastapi import WebSocket

    from lab.agent.agents.agent_interface import AgentInterface
    from lab.config_manager.server import ServerSettings


class ServiceContext:
    """保存单个会话的运行时服务实例。

    该对象负责管理当前连接所需的配置、Agent、Live2D 和翻译引擎，
    并支持根据 `lab.toml` 重新加载运行时状态。
    """

    def __init__(self):
        """初始化默认服务上下文。"""
        self._mcp_connected = False
        self._mcp_lock = asyncio.Lock()
        self.lab_setting: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.server_config: ServerSettings | None = None
        self.character_config: CharacterSettings | None = None

        self.live2d_model: Live2dModel | None = None
        self.agent_engine: AgentInterface | None = None
        self.translate_engine: TranslateEngineRouter | None = None

        self.chat_system_prompt: str | None = None
        self.vision_system_prompt: str | None = None
        self.history_uid: str = ""
        self.live2d_startup_expression_applied: bool = False

    def __str__(self) -> str:
        """返回当前上下文的可读摘要。

        Returns:
            便于日志输出的字符串表示。
        """
        return (
            f"ServiceContext:\n"
            f"  Server Config: {'Loaded' if self.server_config else 'Not Loaded'}\n"
            f"    Details: {json.dumps(self.server_config.model_dump(), indent=6) if self.server_config else 'None'}\n"
            f"  Live2D Model: {self.live2d_model.model_info if self.live2d_model else 'Not Loaded'}\n"
            f"  Chat System Prompt: {self.chat_system_prompt or 'Not Set'}\n"
            f"  Vision System Prompt: {self.vision_system_prompt or 'Not Set'}"
        )

    def load_cache(
        self,
        lab_setting: XnneHangLabSettings,
        server_config: ServerSettings | None,
        character_config: CharacterSettings | None,
        live2d_model: Live2dModel | None,
        agent_engine: AgentInterface,
    ) -> None:
        """复用已初始化的服务对象。

        Args:
            lab_setting: 当前实验室配置。
            server_config: 服务端配置。
            character_config: 当前角色运行时配置。
            live2d_model: 已初始化的 Live2D 模型。
            agent_engine: 已初始化的 Agent 引擎。

        Raises:
            ValueError: 当 `server_config` 为空时抛出。
        """
        if server_config is None:
            raise ValueError("server_config cannot be None")

        self.lab_setting = lab_setting
        self.server_config = server_config
        self.character_config = character_config
        self.live2d_model = live2d_model
        self.agent_engine = agent_engine
        self.live2d_startup_expression_applied = False
        self.init_translate(lab_setting)
        logger.debug("Loaded service context with cache: {}", character_config)

    def _resolve_profile_path(self, config: XnneHangLabSettings, profile_path_str: str) -> Path:
        """解析 profile 文件路径。

        Args:
            config: 完整配置对象。
            profile_path_str: 配置中的 profile 路径。

        Returns:
            基于 `root_dir` 解析后的绝对路径或工作区路径。
        """
        profile_path = Path(profile_path_str)
        if not profile_path.is_absolute():
            profile_path = Path(config.root.root_dir) / profile_path
        return profile_path

    def _load_active_profile(self, config: XnneHangLabSettings) -> Profile | None:
        """加载当前激活的 VTuber profile。

        Args:
            config: 完整配置对象。

        Returns:
            解析成功的 `Profile`；若未配置或加载失败则返回 `None`。
        """
        profile_path_str = config.agent.memory_agent_profile
        if not profile_path_str:
            return None

        profile_path = self._resolve_profile_path(config, profile_path_str)
        if not profile_path.exists():
            logger.warning("Active memory_agent_profile not found: {}", profile_path)
            return None

        try:
            return Profile.from_toml(profile_path)
        except Exception as exc:
            logger.warning("Failed to load profile {}: {}", profile_path, exc)
            return None

    @staticmethod
    def _to_character_settings(profile: Profile | None) -> CharacterSettings | None:
        """将 profile 中的 `[character]` 转成内部运行时结构。

        Args:
            profile: 已加载的 profile。

        Returns:
            内部 `CharacterSettings`；若 profile 未定义 `[character]` 则返回 `None`。
        """
        if profile is None or profile.character is None:
            return None

        char = profile.character
        return CharacterSettings(
            conf_name=char.conf_name,
            conf_uid=char.conf_uid,
            live2d_model_name=char.live2d_model_name or "",
            character_name=char.character_name,
            avatar=char.avatar,
            human_name=char.human_name,
            tts_preprocessor_config=VTuberTTSConfig(
                remove_special_char=char.tts_preprocessor.remove_special_char,
                ignore_brackets=char.tts_preprocessor.ignore_brackets,
                ignore_parentheses=char.tts_preprocessor.ignore_parentheses,
                ignore_asterisks=char.tts_preprocessor.ignore_asterisks,
                ignore_angle_brackets=char.tts_preprocessor.ignore_angle_brackets,
            ),
        )

    async def load_from_config(self, config: XnneHangLabSettings) -> None:
        """根据配置重载运行时上下文。

        由于已经移除了 `lab.toml` 中的角色 fallback，
        当前激活的 `memory_agent_profile` 必须存在且必须包含 `[character]`。

        Args:
            config: 最新的实验室配置。

        Raises:
            ValueError: 当 active profile 未配置、加载失败或缺少 `[character]` 时抛出。
        """
        self.lab_setting = config

        if self.server_config is None:
            self.server_config = config.server

        profile_path_str = config.agent.memory_agent_profile
        if not profile_path_str:
            raise ValueError("memory_agent_profile is not configured")

        profile = self._load_active_profile(config)
        if profile is None:
            raise ValueError(f"Failed to load active profile: {profile_path_str}")

        self.character_config = self._to_character_settings(profile)
        if self.character_config is None:
            raise ValueError(f"Active memory_agent_profile must define [character]: {profile_path_str}")

        live2d_name = self.character_config.live2d_model_name
        if live2d_name:
            t0 = time.perf_counter()
            logger.info("⏳ 初始化 Live2D...")
            self.init_live2d(live2d_name)
            logger.info("✅ Live2D 初始化完成 ({:.1f}s)", time.perf_counter() - t0)
        else:
            logger.info("ℹ️ 当前 profile 未配置 Live2D 模型，跳过 Live2D 初始化")
            self.live2d_model = None

        t1 = time.perf_counter()
        logger.info("⏳ 初始化 Agent（加载 plugins / LLM client）...")
        await self.init_agent(config)
        logger.info("✅ Agent 初始化完成 ({:.1f}s)", time.perf_counter() - t1)

        self.init_translate(config)
        self.server_config = config.server

    def init_live2d(self, live2d_model_name: str | None) -> None:
        """初始化 Live2D 模型。

        Args:
            live2d_model_name: Live2D 模型名；为空时跳过初始化。
        """
        logger.info("Initializing Live2D: {}", live2d_model_name)
        if not live2d_model_name:
            self.live2d_model = None
            self.live2d_startup_expression_applied = False
            if self.character_config is not None:
                self.character_config.live2d_model_name = ""
            logger.info("Current profile does not configure Live2D, skipping initialization.")
            return

        try:
            self.live2d_model = Live2dModel(live2d_model_name)
            if self.character_config is not None:
                self.character_config.live2d_model_name = live2d_model_name
            self.live2d_startup_expression_applied = False
        except Exception as exc:
            logger.critical("Error initializing Live2D: {}", exc)
            logger.critical("Try to proceed without Live2D...")
            self.live2d_model = None

    async def init_agent(self, lab_settings: XnneHangLabSettings) -> None:
        """初始化 Agent 引擎。

        Args:
            lab_settings: 当前实验室配置。

        Raises:
            ValueError: 当 `character_config` 尚未准备好时抛出。
        """
        if self.character_config is None:
            logger.error("character_config is None, cannot create agent.")
            raise ValueError("character_config cannot be None")

        self.agent_engine = await AgentFactory.create_agent(
            lab_setting=lab_settings,
            live2d_model=self.live2d_model,
            tts_preprocessor_config=self.character_config.tts_preprocessor_config,
        )

    async def ensure_mcp_connected(self) -> None:
        """确保 MCP 连接只初始化一次。"""
        if self._mcp_connected or self.agent_engine is None:
            return
        async with self._mcp_lock:
            if self._mcp_connected:
                return
            if self.lab_setting.agent.enable_tool:
                await self.agent_engine.connect_mcp_servers()
            self._mcp_connected = True

    def init_translate(self, lab_settings: XnneHangLabSettings) -> None:
        """初始化或更新翻译引擎。

        Args:
            lab_settings: 当前实验室配置。
        """
        if self.translate_engine is None:
            self.translate_engine = TranslateEngineRouter(lab_settings)
            return

        self.translate_engine.update_settings(lab_settings)

    async def handle_config_switch(
        self,
        websocket: WebSocket,
        config_file_name: str,
    ) -> None:
        """处理配置切换并通知前端。

        Args:
            websocket: 当前 WebSocket 连接。
            config_file_name: 目标配置文件名。

        Raises:
            ValueError: 当配置切换请求非法时抛出。
        """
        try:
            if self.server_config is None:
                logger.error("server_config is None, cannot switch configuration")
                raise ValueError("server_config cannot be None")
            if config_file_name != "lab.toml":
                raise ValueError("Only lab.toml is supported")

            new_config = load_settings_file("lab.toml", XnneHangLabSettings)
            await self.load_from_config(new_config)
            logger.debug("New config: {}", self)
            if self.character_config is not None:
                logger.debug("New character config: {}", self.character_config.model_dump())

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "set-model-and-conf",
                        "model_info": self.live2d_model.model_info if self.live2d_model else None,
                        "conf_name": self.character_config.conf_name if self.character_config else "",
                        "conf_uid": self.character_config.conf_uid if self.character_config else "",
                    }
                )
            )

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "config-switched",
                        "message": "Switched to config: lab.toml",
                    }
                )
            )

            logger.info("Configuration switched to lab.toml")

        except Exception as exc:
            logger.error("Error switching configuration: {}", exc)
            logger.debug(self)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error switching configuration: {str(exc)}",
                    }
                )
            )
            raise
