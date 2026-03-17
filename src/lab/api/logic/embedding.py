from __future__ import annotations

import gc
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any

from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from llama_cpp import Llama

DEFAULT_EMBEDDING_MODEL_NAME = "bge-m3"

try:
    import llama_cpp
    from llama_cpp import Llama
except ImportError:
    llama_cpp = None
    Llama = Any  # type: ignore[assignment,misc]

_embedding_model: Llama | None = None
_embedding_model_path: str | None = None
_embedding_pooling_type: str | None = None
_embedding_n_gpu_layers: int | None = None
_embedding_lock = RLock()


def _get_embedding_settings() -> XnneHangLabSettings:
    return load_settings_file("lab.toml", XnneHangLabSettings)


def resolve_embedding_model_path(
    settings: XnneHangLabSettings | None = None,
    model_path: str | None = None,
) -> Path | None:
    configured_model_path = (model_path or (settings or _get_embedding_settings()).local_embedding.model_path).strip()
    if not configured_model_path:
        return None

    candidate = Path(configured_model_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def is_embedding_model_loaded() -> bool:
    return _embedding_model is not None


def _resolve_pooling_type(pooling_type: str) -> int:
    if llama_cpp is None:
        raise RuntimeError("llama-cpp-python is not installed; install the llama-cpp dependency group first")

    pooling_map = {
        "mean": llama_cpp.LLAMA_POOLING_TYPE_MEAN,
        "cls": llama_cpp.LLAMA_POOLING_TYPE_CLS,
        "last": llama_cpp.LLAMA_POOLING_TYPE_LAST,
    }
    normalized = pooling_type.strip().lower()
    if normalized not in pooling_map:
        raise ValueError(f"Unsupported pooling_type: {pooling_type}")
    return pooling_map[normalized]


def load_embedding_model(
    model_path: str,
    pooling_type: str,
    n_gpu_layers: int,
) -> None:
    global _embedding_model, _embedding_model_path, _embedding_pooling_type, _embedding_n_gpu_layers

    resolved_model_path = resolve_embedding_model_path(model_path=model_path)
    if resolved_model_path is None:
        raise RuntimeError("[local_embedding].model_path is not set in lab.toml")
    if not resolved_model_path.exists():
        raise FileNotFoundError(f"Local embedding model not found: {resolved_model_path}")
    if llama_cpp is None:
        raise RuntimeError("llama-cpp-python is not installed; install the llama-cpp dependency group first")

    normalized_pooling_type = pooling_type.strip().lower()
    pooling_value = _resolve_pooling_type(normalized_pooling_type)

    with _embedding_lock:
        if (
            _embedding_model is not None
            and _embedding_model_path == str(resolved_model_path)
            and _embedding_pooling_type == normalized_pooling_type
            and _embedding_n_gpu_layers == n_gpu_layers
        ):
            return

        logger.info(
            "[LocalEmbedding] Loading model from {} (pooling_type={}, n_gpu_layers={})",
            resolved_model_path,
            normalized_pooling_type,
            n_gpu_layers,
        )
        _embedding_model = Llama(
            model_path=str(resolved_model_path),
            embedding=True,
            pooling_type=pooling_value,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        _embedding_model_path = str(resolved_model_path)
        _embedding_pooling_type = normalized_pooling_type
        _embedding_n_gpu_layers = n_gpu_layers
        logger.info("[LocalEmbedding] Model loaded successfully")


def get_embedding_model() -> Llama:
    if _embedding_model is None:
        raise RuntimeError("Local embedding model is not loaded")
    return _embedding_model


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = get_embedding_model()
    result = model.embed(texts, normalize=True)
    if isinstance(result, list) and result and isinstance(result[0], float):
        return [list(result)]
    return [list(vector) for vector in result]


def unload_embedding_model() -> None:
    global _embedding_model, _embedding_model_path, _embedding_pooling_type, _embedding_n_gpu_layers

    with _embedding_lock:
        _embedding_model = None
        _embedding_model_path = None
        _embedding_pooling_type = None
        _embedding_n_gpu_layers = None
    gc.collect()
