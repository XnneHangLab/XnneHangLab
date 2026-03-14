from __future__ import annotations

import gc
import re
import unicodedata
from importlib import import_module
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, cast

from loguru import logger  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

if TYPE_CHECKING:
    from lab.asr.types import ASRResponse

logger = cast("Any", logger)

_qwen_asr_engines: dict[tuple[str, str, str], QwenASREngine] = {}
_TIMESTAMP_PATTERN = re.compile(r"<\|(\d+(?:\.\d+)?)\|>")


def _normalize_device(device: str) -> str:
    """规范化推理设备名称。

    Args:
        device: 原始设备名称。

    Returns:
        str: 规范化后的设备名称。

    Raises:
        RuntimeError: 设备名非法或 CUDA 不可用时抛出。
    """
    normalized = device.strip().lower() or "cpu"
    if normalized not in {"cpu", "cuda"}:
        raise RuntimeError(f"Unsupported Qwen3-ASR device: {device}")

    if normalized == "cuda":
        torch = _import_torch()
        if not torch.cuda.is_available():
            raise RuntimeError("Qwen3-ASR device is set to cuda, but CUDA is not available.")

    return normalized


def _import_torch() -> Any:
    """延迟导入 torch。

    Args:
        None.

    Returns:
        Any: torch 模块对象。

    Raises:
        RuntimeError: torch 未安装时抛出。
    """
    try:
        torch_module = import_module("torch")
    except ImportError as exc:
        raise RuntimeError("Qwen3-ASR requires torch to be installed.") from exc
    return torch_module  # pyright: ignore[reportUnknownVariableType]


def _import_qwen_asr() -> Any:
    """延迟导入 qwen_asr 官方推理包。

    Args:
        None.

    Returns:
        Any: `qwen_asr.Qwen3ASRModel` 类。

    Raises:
        RuntimeError: qwen-asr 未安装时抛出。
    """
    try:
        qwen_asr_module = import_module("qwen_asr")
    except ImportError as exc:
        raise RuntimeError(
            "Qwen3-ASR requires the `qwen-asr` package. Run `uv sync` after updating dependencies."
        ) from exc
    return qwen_asr_module.Qwen3ASRModel  # pyright: ignore[reportUnknownVariableType,reportAttributeAccessIssue]


def _resolve_model_path(model_path: str) -> str:
    """解析并校验本地模型路径。

    Args:
        model_path: 本地模型目录路径。

    Returns:
        str: 规范化后的本地模型目录。

    Raises:
        RuntimeError: 模型目录不存在时抛出。
    """
    resolved = Path(model_path).expanduser().resolve()
    if not resolved.exists():
        raise RuntimeError(
            f"Qwen3-ASR model path does not exist: {resolved}. "
            "Run `just install-qwen-asr` first or update config/lab.toml."
        )
    return str(resolved)


def _resolve_optional_path(path_value: str | None) -> str:
    """解析可选路径；空值时返回空字符串。

    Args:
        path_value: 可选路径值。

    Returns:
        str: 规范化路径，或空字符串。

    Raises:
        RuntimeError: 路径非空但不存在时抛出。
    """
    if not path_value or not path_value.strip():
        return ""
    return _resolve_model_path(path_value)


def _extract_asr_text(raw_output: str) -> str:
    """提取模型输出中的 ASR 文本主体。

    Args:
        raw_output: 模型原始输出。

    Returns:
        str: 去掉元信息后的识别文本。

    Raises:
        None.
    """
    cleaned = raw_output.strip()
    if not cleaned:
        return ""

    if "<asr_text>" in cleaned:
        meta_part, cleaned = cleaned.split("<asr_text>", 1)
        if "language none" in meta_part.lower() and not cleaned.strip():
            return ""

    return cleaned.strip()


def _is_cjk_char(char: str) -> bool:
    """判断字符是否属于中日韩表意文字。

    Args:
        char: 待判断字符。

    Returns:
        bool: 是否属于中日韩表意文字。

    Raises:
        None.
    """
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF or 0x20000 <= code <= 0x2CEAF
    )


def _tokenize_asr_segment(segment: str) -> list[str]:
    """将文本切成与 ASRResponse 兼容的 token 列表。

    Args:
        segment: 不含时间戳标签的文本片段。

    Returns:
        list[str]: 归一化后的 token 列表。

    Raises:
        None.
    """
    tokens: list[str] = []
    buffer: list[str] = []

    def flush_buffer() -> None:
        if buffer:
            token = "".join(buffer).strip()
            if token:
                tokens.append(token)
            buffer.clear()

    for char in segment:
        if char.isspace():
            flush_buffer()
            continue

        if _is_cjk_char(char):
            flush_buffer()
            tokens.append(char)
            continue

        category = unicodedata.category(char)
        if char.isalnum() or char in {"'", "-", "_"} or category.startswith(("L", "N")):
            buffer.append(char)
            continue

        flush_buffer()
        if tokens:
            tokens[-1] += char
        else:
            tokens.append(char)

    flush_buffer()
    return [token for token in tokens if token]


def _distribute_token_timestamps(tokens: list[str], start_ms: int, end_ms: int) -> list[list[int]]:
    """在时间区间内为 token 分配时间戳。

    Args:
        tokens: token 列表。
        start_ms: 起始时间，单位毫秒。
        end_ms: 结束时间，单位毫秒。

    Returns:
        list[list[int]]: `[[start, end], ...]` 时间戳列表。

    Raises:
        None.
    """
    if not tokens:
        return []

    safe_end_ms = max(start_ms, end_ms)
    total_weight = sum(max(len(token), 1) for token in tokens)
    elapsed_weight = 0
    ranges: list[list[int]] = []

    for index, token in enumerate(tokens):
        token_start = start_ms + round((safe_end_ms - start_ms) * elapsed_weight / total_weight)
        elapsed_weight += max(len(token), 1)
        if index == len(tokens) - 1:
            token_end = safe_end_ms
        else:
            token_end = start_ms + round((safe_end_ms - start_ms) * elapsed_weight / total_weight)
        ranges.append([int(token_start), int(max(token_start, token_end))])

    return ranges


def _build_fallback_response(text: str, audio_duration_ms: int) -> tuple[str, list[list[int]]]:
    """在缺少原生时间戳时构造保底结果。

    Args:
        text: 识别文本。
        audio_duration_ms: 音频总时长，单位毫秒。

    Returns:
        tuple[str, list[list[int]]]: 空格分隔文本和毫秒级时间戳。

    Raises:
        None.
    """
    tokens = _tokenize_asr_segment(text)
    if not tokens:
        return "", []

    timestamps = _distribute_token_timestamps(tokens, 0, max(0, audio_duration_ms))
    logger.warning("Qwen3-ASR output has no native timestamps; fallback token timestamps were generated.")  # pyright: ignore[reportUnknownMemberType]
    return " ".join(tokens), timestamps


def parse_qwen_asr_output(raw_output: str, audio_duration_ms: int) -> tuple[str, list[list[int]]]:
    """解析带 `<|0.00|>` 标签的 Qwen3-ASR 文本输出。

    Args:
        raw_output: 模型原始输出文本。
        audio_duration_ms: 音频总时长，单位毫秒。

    Returns:
        tuple[str, list[list[int]]]: 空格分隔文本和毫秒级时间戳。

    Raises:
        None.
    """
    text_body = _extract_asr_text(raw_output)
    if not text_body:
        return "", []

    matches = list(_TIMESTAMP_PATTERN.finditer(text_body))
    if not matches:
        return _build_fallback_response(text_body, audio_duration_ms)

    tokens: list[str] = []
    timestamps: list[list[int]] = []
    previous_time_ms = 0
    previous_end = 0

    for match in matches:
        current_time_ms = int(round(float(match.group(1)) * 1000))
        segment = text_body[previous_end : match.start()]
        segment_tokens = _tokenize_asr_segment(segment)
        if segment_tokens:
            tokens.extend(segment_tokens)
            timestamps.extend(_distribute_token_timestamps(segment_tokens, previous_time_ms, current_time_ms))
        previous_time_ms = current_time_ms
        previous_end = match.end()

    trailing_segment = text_body[previous_end:]
    trailing_tokens = _tokenize_asr_segment(trailing_segment)
    if trailing_tokens:
        tokens.extend(trailing_tokens)
        timestamps.extend(
            _distribute_token_timestamps(
                trailing_tokens,
                previous_time_ms,
                max(previous_time_ms, audio_duration_ms),
            )
        )

    if not tokens or len(tokens) != len(timestamps):
        return _build_fallback_response(text_body, audio_duration_ms)

    return " ".join(tokens), timestamps


def _normalize_result_text(result: Any) -> str:
    """从官方结果对象中提取文本。

    Args:
        result: `qwen-asr` 返回的单条结果对象。

    Returns:
        str: 识别文本。

    Raises:
        None.
    """
    for key in ("text", "transcript", "prediction"):
        value = getattr(result, key, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    result_dict = cast("dict[str, Any] | None", result if isinstance(result, dict) else None)
    if result_dict is not None:
        for key in ("text", "transcript", "prediction"):
            value = result_dict.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _extract_timestamp_span(item: Any) -> tuple[int, int] | None:
    """从官方时间戳条目中提取起止毫秒。

    Args:
        item: 时间戳条目。

    Returns:
        tuple[int, int] | None: 起止毫秒；无法解析时返回 None。

    Raises:
        None.
    """
    start: Any = None
    end: Any = None

    item_dict = cast("dict[str, Any] | None", item if isinstance(item, dict) else None)
    if item_dict is not None:
        start = item_dict.get("start") or item_dict.get("start_time") or item_dict.get("begin")
        end = item_dict.get("end") or item_dict.get("end_time") or item_dict.get("finish")
    elif isinstance(item, list):
        item_sequence = cast("list[Any]", item)
        if len(item_sequence) < 2:
            return None
        start, end = item_sequence[0], item_sequence[1]
    elif isinstance(item, tuple):
        item_sequence = cast("tuple[Any, ...]", item)
        if len(item_sequence) < 2:
            return None
        start, end = item_sequence[0], item_sequence[1]
    else:
        item_obj = cast("Any", item)
        start = getattr(item_obj, "start", None) or getattr(item_obj, "start_time", None)
        end = getattr(item_obj, "end", None) or getattr(item_obj, "end_time", None)

    if start is None or end is None:
        return None

    try:
        start_value = float(start)
        end_value = float(end)
    except (TypeError, ValueError):
        return None

    # Official outputs are in seconds; tolerate ms-like integers just in case.
    if start_value > 1000 or end_value > 1000:
        start_ms = int(round(start_value))
        end_ms = int(round(end_value))
    else:
        start_ms = int(round(start_value * 1000))
        end_ms = int(round(end_value * 1000))

    return start_ms, max(start_ms, end_ms)


def _normalize_native_response(result: Any, audio_duration_ms: int) -> tuple[str, list[list[int]]]:
    """将官方 `qwen-asr` 结果转换为项目标准输出。

    Args:
        result: 官方推理结果对象。
        audio_duration_ms: 音频总时长，单位毫秒。

    Returns:
        tuple[str, list[list[int]]]: 空格分隔文本和毫秒级时间戳。

    Raises:
        None.
    """
    text = _normalize_result_text(result)
    if not text:
        return "", []

    raw_timestamps: Any = getattr(result, "time_stamps", None)
    result_dict = cast("dict[str, Any] | None", result if isinstance(result, dict) else None)
    if raw_timestamps is None and result_dict is not None:
        raw_timestamps = result_dict.get("time_stamps") or result_dict.get("timestamps")
    if raw_timestamps is not None and hasattr(raw_timestamps, "items"):
        raw_timestamps = list(raw_timestamps.items)

    if not isinstance(raw_timestamps, list) or not raw_timestamps:
        return _build_fallback_response(text, audio_duration_ms)
    raw_timestamp_items = cast("list[Any]", raw_timestamps)

    tokens: list[str] = []
    timestamps: list[list[int]] = []
    whole_text_tokens = _tokenize_asr_segment(text)

    for item in raw_timestamp_items:
        span = _extract_timestamp_span(item)
        item_text = ""
        item_dict = cast("dict[str, Any] | None", item if isinstance(item, dict) else None)
        if item_dict is not None:
            item_text = str(item_dict.get("text", "")).strip()
        else:
            item_text = str(getattr(cast("Any", item), "text", "")).strip()

        if span is None:
            continue

        start_ms, end_ms = span
        item_tokens = _tokenize_asr_segment(item_text) if item_text else []
        if not item_tokens:
            continue

        tokens.extend(item_tokens)
        timestamps.extend(_distribute_token_timestamps(item_tokens, start_ms, end_ms))

    if tokens and len(tokens) == len(timestamps):
        return " ".join(tokens), timestamps

    if whole_text_tokens:
        return _build_fallback_response(text, audio_duration_ms)

    return "", []


class QwenASREngine:
    """Qwen3-ASR 推理引擎。

    Args:
        model_path: 本地模型目录路径。
        device: 推理设备，支持 `cpu` 或 `cuda`。
        forced_aligner_path: 可选的 Forced Aligner 模型路径。
    """

    def __init__(self, model_path: str, device: str = "cpu", forced_aligner_path: str | None = None) -> None:
        """初始化 Qwen3-ASR 推理引擎。

        Args:
            model_path: 本地模型目录路径。
            device: 推理设备。
            forced_aligner_path: 可选的 Forced Aligner 模型路径。

        Returns:
            None.

        Raises:
            RuntimeError: 模型或依赖加载失败时抛出。
        """
        self.model_path = _resolve_model_path(model_path)
        self.device = _normalize_device(device)
        self.forced_aligner_path = _resolve_optional_path(forced_aligner_path)
        self._lock = Lock()
        self._torch = _import_torch()
        qwen_asr_model_cls = _import_qwen_asr()

        load_kwargs: dict[str, Any] = {}
        if self.forced_aligner_path:
            load_kwargs["forced_aligner"] = self.forced_aligner_path
            load_kwargs["forced_aligner_kwargs"] = {}

        load_attempts = [
            {"device_map": self.device},
            {},
        ]

        last_exc: Exception | None = None
        for extra_kwargs in load_attempts:
            try:
                self._model = qwen_asr_model_cls.from_pretrained(
                    self.model_path,
                    **load_kwargs,
                    **extra_kwargs,
                )
                break
            except TypeError as exc:
                if "device_map" not in str(exc):
                    raise
                last_exc = exc
                continue
            except Exception as exc:
                raise RuntimeError(f"Failed to load Qwen3-ASR model from {self.model_path}") from exc
        else:
            raise RuntimeError("Failed to initialize Qwen3-ASR with the available loader signatures.") from last_exc

    def transcribe(self, audio_path: Path) -> ASRResponse:
        """对音频执行 ASR 推理。

        Args:
            audio_path: 输入音频文件路径。

        Returns:
            ASRResponse: 包含 `key`、`text`、`timestamp` 的识别结果。

        Raises:
            FileNotFoundError: 音频文件不存在时抛出。
            RuntimeError: 推理失败时抛出。
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        with self._lock:
            try:
                results = self._model.transcribe(
                    audio=str(audio_path),
                    return_time_stamps=bool(self.forced_aligner_path),
                )
            except TypeError as exc:
                if "audio" not in str(exc):
                    raise
                try:
                    results = self._model.transcribe(
                        str(audio_path),
                        return_time_stamps=bool(self.forced_aligner_path),
                    )
                except Exception as exc:
                    logger.exception(f"Qwen3-ASR transcribe failed for {audio_path}")  # pyright: ignore[reportUnknownMemberType]
                    raise RuntimeError(f"Failed to transcribe audio with Qwen3-ASR: {audio_path}") from exc
            except Exception as exc:
                logger.exception(f"Qwen3-ASR transcribe failed for {audio_path}")  # pyright: ignore[reportUnknownMemberType]
                raise RuntimeError(f"Failed to transcribe audio with Qwen3-ASR: {audio_path}") from exc

        if not isinstance(results, list) or not results:
            raise RuntimeError(f"Qwen3-ASR returned an empty response for: {audio_path}")

        result = cast("Any", results[0])
        audio_duration_ms = 0
        result_dict = cast("dict[str, Any] | None", result if isinstance(result, dict) else None)
        if result_dict is not None:
            duration_value = result_dict.get("audio_duration") or result_dict.get("duration")
        else:
            result_obj = cast("Any", result)
            duration_value = getattr(result_obj, "audio_duration", None) or getattr(result_obj, "duration", None)
        if isinstance(duration_value, (int, float)):
            audio_duration_ms = int(
                round(float(duration_value) * 1000 if float(duration_value) <= 1000 else float(duration_value))
            )

        text, timestamps = _normalize_native_response(result, audio_duration_ms=audio_duration_ms)
        return {
            "key": audio_path.stem,
            "text": text,
            "timestamp": timestamps,
        }


def load_qwen_asr(model_path: str, device: str, forced_aligner_path: str | None = None) -> QwenASREngine:
    """加载或返回缓存的 Qwen3-ASR 引擎。

    Args:
        model_path: 本地模型目录路径。
        device: 推理设备。
        forced_aligner_path: 可选的 Forced Aligner 模型路径。

    Returns:
        QwenASREngine: 已初始化的引擎实例。

    Raises:
        RuntimeError: 引擎初始化失败时抛出。
    """
    resolved_model_path = _resolve_model_path(model_path)
    resolved_aligner_path = _resolve_optional_path(forced_aligner_path)
    normalized_device = _normalize_device(device)
    cache_key = (resolved_model_path, resolved_aligner_path, normalized_device)
    engine = _qwen_asr_engines.get(cache_key)
    if engine is None:
        engine = QwenASREngine(
            model_path=resolved_model_path,
            device=normalized_device,
            forced_aligner_path=resolved_aligner_path or None,
        )
        _qwen_asr_engines[cache_key] = engine
    return engine


def get_qwen_asr(model_path: str, device: str, forced_aligner_path: str | None = None) -> QwenASREngine:
    """获取已加载的 Qwen3-ASR 引擎。

    Args:
        model_path: 本地模型目录路径。
        device: 推理设备。
        forced_aligner_path: 可选的 Forced Aligner 模型路径。

    Returns:
        QwenASREngine: 已初始化的引擎实例。

    Raises:
        RuntimeError: 指定引擎尚未加载时抛出。
    """
    resolved_model_path = _resolve_model_path(model_path)
    resolved_aligner_path = _resolve_optional_path(forced_aligner_path)
    normalized_device = _normalize_device(device)
    cache_key = (resolved_model_path, resolved_aligner_path, normalized_device)
    engine = _qwen_asr_engines.get(cache_key)
    if engine is None:
        raise RuntimeError(
            "Qwen3-ASR engine is not loaded: "
            f"model_path={resolved_model_path}, forced_aligner_path={resolved_aligner_path or 'None'}, device={normalized_device}."
        )
    return engine


def reset_qwen_asr_engine(
    model_path: str | None = None, device: str | None = None, forced_aligner_path: str | None = None
) -> None:
    """重置 Qwen3-ASR 引擎缓存。

    Args:
        model_path: 指定模型路径；为 `None` 时清空全部缓存。
        device: 指定设备；仅在 `model_path` 也提供时生效。
        forced_aligner_path: 指定 Forced Aligner 路径。

    Returns:
        None.

    Raises:
        None.
    """
    if model_path is None:
        _qwen_asr_engines.clear()
    else:
        resolved_model_path = _resolve_model_path(model_path)
        resolved_aligner_path = _resolve_optional_path(forced_aligner_path)
        normalized_device = _normalize_device(device or "cpu")
        _qwen_asr_engines.pop((resolved_model_path, resolved_aligner_path, normalized_device), None)

    gc.collect()

    try:
        torch = _import_torch()
    except RuntimeError:
        return

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
