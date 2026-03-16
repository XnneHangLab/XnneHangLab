from __future__ import annotations

import gc
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, ClassVar

from loguru import logger

if TYPE_CHECKING:
    from llama_cpp import Llama


class LLMTranslateEngine:
    """Local LLM translation engine backed by llama-cpp-python."""

    _instance: ClassVar[LLMTranslateEngine | None] = None
    _lock: ClassVar[RLock] = RLock()
    _language_map: ClassVar[dict[str, str]] = {
        "EN": "English",
        "ZH": "Chinese",
        "JA": "Japanese",
        "FR": "French",
        "DE": "German",
        "ES": "Spanish",
        "PT": "Portuguese",
        "RU": "Russian",
        "KO": "Korean",
        "AR": "Arabic",
        "TH": "Thai",
        "VI": "Vietnamese",
        "IT": "Italian",
    }

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._instance is not None

    @classmethod
    def get_instance(
        cls,
        model_path: str | Path | None = None,
        n_gpu_layers: int = 0,
        n_ctx: int = 2048,
    ) -> LLMTranslateEngine:
        """Return the singleton engine instance, loading the model only once."""
        resolved_model_path = str(Path(model_path).expanduser().resolve()) if model_path is not None else None

        with cls._lock:
            if cls._instance is None:
                if resolved_model_path is None:
                    raise ValueError("model_path is required when creating the translate engine")
                cls._instance = cls(
                    model_path=resolved_model_path,
                    n_gpu_layers=n_gpu_layers,
                    n_ctx=n_ctx,
                )
            elif resolved_model_path is not None and (
                cls._instance.model_path != resolved_model_path
                or cls._instance.n_gpu_layers != n_gpu_layers
                or cls._instance.n_ctx != n_ctx
            ):
                logger.info(
                    "[LLMTranslate] Engine configuration changed, reloading model: {}",
                    resolved_model_path,
                )
                cls._instance.unload()
                cls._instance = cls(
                    model_path=resolved_model_path,
                    n_gpu_layers=n_gpu_layers,
                    n_ctx=n_ctx,
                )

            return cls._instance

    def __init__(self, model_path: str, n_gpu_layers: int = 0, n_ctx: int = 2048):
        """Initialize the engine and load the GGUF model."""
        model_file = Path(model_path).expanduser().resolve()
        if not model_file.exists():
            raise FileNotFoundError(f"LLM translate model not found: {model_file}")

        from llama_cpp import Llama

        self.model_path = str(model_file)
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self._llm: Llama | None = None

        logger.info(
            "[LLMTranslate] Loading model from {} (n_gpu_layers={}, n_ctx={})",
            self.model_path,
            self.n_gpu_layers,
            self.n_ctx,
        )
        self._llm = Llama(
            model_path=self.model_path,
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            verbose=False,
        )
        logger.info("[LLMTranslate] Model loaded successfully")

    def translate(self, text: str, target_language: str = "ZH") -> str:
        """Translate text into the target language."""
        if self._llm is None:
            raise RuntimeError("LLM translate model is not loaded")

        normalized_target = target_language.strip().upper()
        target_language_name = self._language_map.get(normalized_target, normalized_target)

        logger.info(
            "[LLMTranslate] Translating text (target={}, chars={})",
            normalized_target,
            len(text),
        )

        response: Any = self._llm.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": f"Translate to {target_language_name}. Output translation only.",
                },
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=512,
        )
        translated_text = self._extract_content(response).strip()
        logger.info("[LLMTranslate] Translation completed (chars={})", len(translated_text))
        return translated_text

    def unload(self) -> None:
        """Unload the model and release memory."""
        with type(self)._lock:
            logger.info("[LLMTranslate] Unloading model from {}", self.model_path)
            model = self._llm
            self._llm = None

            close = getattr(model, "close", None)
            if callable(close):
                close()

            if type(self)._instance is self:
                type(self)._instance = None

        gc.collect()
        logger.info("[LLMTranslate] Model unloaded")

    @classmethod
    def unload_instance(cls) -> None:
        engine = cls._instance
        if engine is None:
            logger.debug("[LLMTranslate] unload skipped: engine is not loaded")
            return

        engine.unload()

    @classmethod
    def _extract_content(cls, response: dict[str, Any]) -> str:
        choices = response.get("choices", [])
        if not choices:
            raise ValueError("No choices returned from llama-cpp response")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not isinstance(content, str):
            raise TypeError("Expected string content from llama-cpp chat completion response")
        return content
