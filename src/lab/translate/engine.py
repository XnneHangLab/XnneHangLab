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
        self._model: Llama | None = None

        logger.info(
            "[LLMTranslate] Loading model from {} (n_gpu_layers={}, n_ctx={})",
            self.model_path,
            self.n_gpu_layers,
            self.n_ctx,
        )
        self._model = Llama(
            model_path=self.model_path,
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            verbose=False,
        )
        logger.info("[LLMTranslate] Model loaded successfully")

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """Translate text between language codes."""
        if self._model is None:
            raise RuntimeError("LLM translate model is not loaded")

        normalized_source = source_language.strip().upper()
        normalized_target = target_language.strip().upper()
        source_language_name = self._language_map.get(normalized_source, normalized_source)
        target_language_name = self._language_map.get(normalized_target, normalized_target)

        logger.info(
            "[LLMTranslate] Translating text ({} -> {}, chars={})",
            normalized_source,
            normalized_target,
            len(text),
        )

        response: Any = self._model.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional translator. "
                        "Output the translation only, no explanation, no original text."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Translate the following {source_language_name} text to {target_language_name}:\n\n{text}",
                },
            ],
            temperature=0.3,
            max_tokens=512,
        )
        translated_text = self._extract_content(response).strip()
        logger.info("[LLMTranslate] Translation completed (chars={})", len(translated_text))
        return translated_text

    def unload(self) -> None:
        """Unload the model and release memory."""
        with type(self)._lock:
            logger.info("[LLMTranslate] Unloading model from {}", self.model_path)
            model = self._model
            self._model = None

            close = getattr(model, "close", None)
            if callable(close):
                close()

            if type(self)._instance is self:
                type(self)._instance = None

        gc.collect()
        logger.info("[LLMTranslate] Model unloaded")

    @classmethod
    def _extract_content(cls, response: dict[str, Any]) -> str:
        choices = response.get("choices", [])
        if not choices:
            raise ValueError("No choices returned from llama-cpp response")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_segments: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text_segments.append(str(item.get("text", "")))
                else:
                    text_segments.append(str(item))
            return "".join(text_segments)

        return str(content)
