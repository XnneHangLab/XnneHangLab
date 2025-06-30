from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from lab.config_manager.vtuber import (
    AgentConfig,
    CharacterConfig,
    Config,
    SystemConfig,
    TranslatorConfig,
    read_yaml,
    validate_config,
)
from lab.live2d_model import Live2dModel

if TYPE_CHECKING:
    from fastapi import WebSocket


class ServiceContext:
    """Initializes, stores, and updates the asr, tts, and llm instances and other
    configurations for a connected client."""

    def __init__(self):
        self.config: Config | None = None
        self.system_config: SystemConfig | None = None
        self.character_config: CharacterConfig | None = None

        self.live2d_model: Live2dModel | None = None

        # the system prompt is a combination of the persona prompt and live2d expression prompt
        self.system_prompt: str | None = None

        self.history_uid: str = ""  # Add history_uid field

    def __str__(self):
        return (
            f"ServiceContext:\n"
            f"  System Config: {'Loaded' if self.system_config else 'Not Loaded'}\n"
            f"    Details: {json.dumps(self.system_config.model_dump(), indent=6) if self.system_config else 'None'}\n"
            f"  Live2D Model: {self.live2d_model.model_info if self.live2d_model else 'Not Loaded'}\n"  # type: ignore
            f"  System Prompt: {self.system_prompt or 'Not Set'}"
        )

    # ==== Initializers

    def load_cache(
        self,
        config: Config,
        system_config: SystemConfig,
        character_config: CharacterConfig,
        live2d_model: Live2dModel,
    ) -> None:
        """
        Load the ServiceContext with the reference of the provided instances.
        Pass by reference so no reinitialization will be done.
        """
        if not character_config:
            raise ValueError("character_config cannot be None")
        if not system_config:
            raise ValueError("system_config cannot be None")

        self.config = config
        self.system_config = system_config
        self.character_config = character_config
        self.live2d_model = live2d_model

        logger.debug(f"Loaded service context with cache: {character_config}")

    def load_from_config(self, config: Config) -> None:
        """
        Load the ServiceContext with the config.
        Reinitialize the instances if the config is different.

        Parameters:
        - config (Dict): The configuration dictionary.
        """
        if not self.config:
            self.config = config

        if not self.system_config:
            self.system_config = config.system_config

        if not self.character_config:
            self.character_config = config.character_config

        # update all sub-configs

        # init live2d from character config
        self.init_live2d(config.character_config.live2d_model_name)

        # # init asr from character config
        # self.init_asr(config.character_config.asr_config)

        # # init tts from character config
        # self.init_tts(config.character_config.tts_config)

        # init vad from character config
        # self.init_vad(config.character_config.vad_config)

        # init agent from character config
        self.init_agent(
            config.character_config.agent_config,
            config.character_config.persona_prompt,
        )

        self.init_translate(config.character_config.tts_preprocessor_config.translator_config)

        # store typed config references
        self.config = config
        self.system_config = config.system_config or self.system_config
        self.character_config = config.character_config

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

    def init_agent(self, agent_config: AgentConfig, persona_prompt: str) -> None:
        """Initialize or update the LLM engine based on agent configuration."""
        logger.info(f"Initializing Agent: {agent_config.conversation_agent_choice}")

    def init_translate(self, translator_config: TranslatorConfig) -> None:
        """Initialize or update the translation engine based on the configuration."""

        logger.info("Translation already initialized with the same config.")

    async def handle_config_switch(
        self,
        websocket: WebSocket,
        config_file_name: str,
    ) -> None:
        """
        Handle the configuration switch request.
        Change the configuration to a new config and notify the client.

        Parameters:
        - websocket (WebSocket): The WebSocket connection.
        - config_file_name (str): The name of the configuration file.
        """
        try:
            if self.character_config is None:
                logger.error("character_config is None, cannot switch configuration")
                raise ValueError("character_config cannot be None")
            if self.system_config is None:
                logger.error("system_config is None, cannot switch configuration")
                raise ValueError("system_config cannot be None")
            if self.config is None:
                logger.error("character_config is None, cannot switch configuration")
                raise ValueError("character_config cannot be None")
            new_character_config_data = None

            if config_file_name == "vtuber.yaml":
                # Load base config
                new_character_config_data = read_yaml("config/vtuber.yaml").get("character_config")
            else:
                # Load alternative config and merge with base config
                characters_dir = Path(self.system_config.config_alts_dir)
                file_path = os.path.normpath(characters_dir / config_file_name)
                # if not file_path.startswith(characters_dir):
                #     raise ValueError("Invalid configuration file path")

                alt_config_data = read_yaml(file_path).get("character_config")

                # Start with original config data and perform a deep merge
                new_character_config_data = deep_merge(self.config.character_config.model_dump(), alt_config_data)  # type: ignore

            if new_character_config_data:
                new_config = {
                    "system_config": self.system_config.model_dump(),
                    "character_config": new_character_config_data,
                }
                new_config = validate_config(new_config)
                self.load_from_config(new_config)
                logger.debug(f"New config: {self}")
                logger.debug(f"New character config: {self.character_config.model_dump()}")

                # Send responses to client

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
                            "message": f"Switched to config: {config_file_name}",
                        }
                    )
                )

                logger.info(f"Configuration switched to {config_file_name}")
            else:
                raise ValueError(f"Failed to load configuration from {config_file_name}")

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


def deep_merge(dict1: dict[Any, Any], dict2: dict[Any, Any]) -> dict[Any, Any]:
    """
    Recursively merges dict2 into dict1, prioritizing values from dict2.
    """
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)  # type: ignore
        else:
            result[key] = value
    return result
