from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from loguru import logger

from lab.agent.agent_factory import AgentFactory
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.live2d_model import Live2dModel

if TYPE_CHECKING:
    from fastapi import WebSocket

    from lab.agent.agents.agent_interface import AgentInterface
    from lab.config_manager.server import ServerSettings
    from lab.config_manager.vtuber import CharacterSettings


class ServiceContext:
    """Initializes, stores, and updates the asr, tts, and llm instances and other
    configurations for a connected client."""

    def __init__(self):
        self._mcp_connected = False
        self._mcp_lock = asyncio.Lock()
        self.lab_setting: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.server_config: ServerSettings | None = None
        self.character_config: CharacterSettings | None = None

        self.live2d_model: Live2dModel | None = None
        self.agent_engine: AgentInterface | None = None

        # the system prompt is a combination of the persona prompt and live2d expression prompt
        self.chat_system_prompt: str | None = None
        self.vision_system_prompt: str | None = None
        # self.mcp_handlers: list[MCPHandlerInterface]
        self.history_uid: str = ""  # Add history_uid field

    def __str__(self):
        return (
            f"ServiceContext:\n"
            f"  Server Config: {'Loaded' if self.server_config else 'Not Loaded'}\n"
            f"    Details: {json.dumps(self.server_config.model_dump(), indent=6) if self.server_config else 'None'}\n"
            f"  Live2D Model: {self.live2d_model.model_info if self.live2d_model else 'Not Loaded'}\n"  # type: ignore
            f"  Chat System Prompt: {self.chat_system_prompt or 'Not Set'}\n"
            f"  Vision System Prompt: {self.vision_system_prompt or 'Not Set'}"
        )

    # ==== Initializers

    def load_cache(
        self,
        lab_setting: XnneHangLabSettings,
        server_config: ServerSettings | None,
        character_config: CharacterSettings | None,
        live2d_model: Live2dModel,
        agent_engine: AgentInterface,
    ) -> None:
        """
        Load the ServiceContext with the reference of the provided instances.
        Pass by reference so no reinitialization will be done.
        """
        if character_config is None:
            raise ValueError("character_config cannot be None")
        if server_config is None:
            raise ValueError("server_config cannot be None")

        self.lab_setting = lab_setting
        self.server_config = server_config
        self.character_config = character_config
        self.live2d_model = live2d_model
        self.agent_engine = agent_engine
        logger.debug(f"Loaded service context with cache: {character_config}")

    async def load_from_config(self, config: XnneHangLabSettings) -> None:
        """
        Load the ServiceContext with the config.
        Reinitialize the instances if the config is different.

        Parameters:
        - config (XnneHangLabSettings): The typed lab settings to load into the context.
        """
        self.lab_setting = config

        if self.server_config is None:
            self.server_config = config.server

        if self.character_config is None:
            self.character_config = config.vtuber.character_config

        # update all sub-configs

        # init live2d from character config
        self.init_live2d(config.vtuber.character_config.live2d_model_name)

        # init agent from character config
        await self.init_agent(config)

        # self.init_translate(config.vtuber.character_config.tts_preprocessor_config.translator_config) # 到时替换成自己的
        # store typed config references
        self.server_config = config.server
        self.character_config = config.vtuber.character_config

    def init_live2d(self, live2d_model_name: str) -> None:
        logger.info(f"Initializing Live2D: {live2d_model_name}")
        if self.character_config is None:
            logger.error("character_config is None, cannot initialize live2d")
            raise ValueError("character_config cannot be None")
        try:
            self.live2d_model = Live2dModel(live2d_model_name)
            self.character_config.live2d_model_name = live2d_model_name
        except Exception as e:
            logger.critical(f"Error initializing Live2D: {e}")
            logger.critical("Try to proceed without Live2D...")

    async def init_agent(self, lab_settings: XnneHangLabSettings) -> None:
        """Initialize or update the LLM engine based on agent configuration."""
        if self.live2d_model is None:
            logger.error("Live2D model is not initialized, cannot create agent.")
            raise ValueError("Live2D model must be initialized before creating agent.")
        if self.character_config is None:
            logger.error("character_config is None, cannot create agent.")
            raise ValueError("character_config cannot be None")

        self.agent_engine = await AgentFactory.create_agent(
            lab_setting=lab_settings,
            live2d_model=self.live2d_model,
            tts_preprocessor_config=self.character_config.tts_preprocessor_config,
        )

    async def ensure_mcp_connected(self) -> None:
        if self._mcp_connected or self.agent_engine is None:
            return
        async with self._mcp_lock:
            if self._mcp_connected:  # double-check
                return
            lab_settings = self.lab_setting
            if lab_settings.agent.enable_tool:
                await self.agent_engine.connect_mcp_servers()
            self._mcp_connected = True

    def init_translate(self) -> None:
        """Initialize or update the translation engine based on the configuration."""
        logger.info("Translation already initialized with the same config.")

    async def handle_config_switch(
        self,
        websocket: WebSocket,
        config_file_name: str,
    ) -> None:
        """
        处理配置切换请求。

        当前仅支持使用 `lab.toml` 作为唯一配置源。
        """
        try:
            if self.character_config is None:
                logger.error("character_config is None, cannot switch configuration")
                raise ValueError("character_config cannot be None")
            if self.server_config is None:
                logger.error("server_config is None, cannot switch configuration")
                raise ValueError("server_config cannot be None")
            if config_file_name != "lab.toml":
                raise ValueError("Only lab.toml is supported")

            new_config = load_settings_file(
                "lab.toml", XnneHangLabSettings
            )  # 这里实际上欲盖弥彰，因为我们并没有提供额外的配置文件，config switch 暂时只能切换到 lab.toml。
            await self.load_from_config(new_config)
            logger.debug(f"New config: {self}")
            logger.debug(f"New character config: {self.character_config.model_dump()}")

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "set-model-and-conf",
                        "model_info": self.live2d_model.model_info,  # type: ignore
                        "conf_name": self.character_config.conf_name,
                        "conf_uid": self.character_config.conf_uid,
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

        except Exception as e:
            logger.error(f"Error switching configuration: {e}")
            logger.debug(self)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error switching configuration: {str(e)}",
                    }
                )
            )
            raise e
