from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from lab.api.clients import DeepLXClient, DeepLXRequest, LLMTranslateClient, LLMTranslateRequest

if TYPE_CHECKING:
    from lab.config_manager import XnneHangLabSettings
    from lab.config_manager.agent import TranslateProvider


class TranslateEngineRouter:
    def __init__(self, settings: XnneHangLabSettings):
        self._deeplx_client: DeepLXClient | None = None
        self._llm_client: LLMTranslateClient | None = None
        self.update_settings(settings)

    def update_settings(self, settings: XnneHangLabSettings) -> None:
        self.settings = settings
        self.provider: TranslateProvider = settings.agent.translate_provider
        logger.info("Translation provider set to {}", self.provider)

    async def translate(self, text: str, target_language: str) -> str:
        logger.debug(
            "[TranslateRouter] provider={} -> {}",
            self.provider,
            target_language,
        )

        if self.provider == "deeplx":
            if self._deeplx_client is None:
                self._deeplx_client = DeepLXClient()
            response = await self._deeplx_client.asyncpost(
                DeepLXRequest(
                    text=text,
                    source_language="auto",
                    target_language=target_language,
                )
            )
        else:
            if self._llm_client is None:
                self._llm_client = LLMTranslateClient()
            response = await self._llm_client.asyncpost(
                LLMTranslateRequest(
                    text=text,
                    target_language=target_language,
                )
            )

        if response is None:
            raise RuntimeError(f"Translation failed with provider: {self.provider}")

        return response["target_text"]
