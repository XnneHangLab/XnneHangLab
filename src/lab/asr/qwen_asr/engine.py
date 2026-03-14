# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingTypeArgument=false, reportMissingImports=false

from __future__ import annotations

import gc
import re
import unicodedata
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

import numpy as np
from loguru import logger

if TYPE_CHECKING:
    from lab.asr.types import ASRResponse

_qwen_asr_engines: dict[tuple[str, str], QwenASREngine] = {}
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
        import torch
    except ImportError as exc:
        raise RuntimeError("Qwen3-ASR requires torch to be installed.") from exc
    return torch


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


def _load_audio(audio_path: Path, target_sample_rate: int) -> np.ndarray:
    """读取并重采样音频为单声道 waveform。

    Args:
        audio_path: 输入音频文件路径。
        target_sample_rate: 目标采样率。

    Returns:
        np.ndarray: float32 单声道音频数组。

    Raises:
        RuntimeError: 音频读取失败时抛出。
    """
    try:
        import torchaudio

        waveform, sample_rate = torchaudio.load(str(audio_path))
        if waveform.ndim > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        waveform = waveform.squeeze(0)
        if sample_rate != target_sample_rate:
            waveform = torchaudio.functional.resample(waveform, sample_rate, target_sample_rate)
        audio = waveform.detach().cpu().numpy().astype(np.float32, copy=False)
    except Exception:
        try:
            import librosa

            audio, sample_rate = librosa.load(str(audio_path), sr=None, mono=False)
            audio = np.asarray(audio, dtype=np.float32)
            if audio.ndim > 1:
                audio = np.mean(audio, axis=0, dtype=np.float32)
            if sample_rate != target_sample_rate:
                audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=target_sample_rate).astype(np.float32)
        except Exception as exc:
            raise RuntimeError(f"Failed to load audio file: {audio_path}") from exc

    if audio.ndim != 1:
        audio = np.reshape(audio, (-1,)).astype(np.float32, copy=False)

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 1.0:
        audio = audio / peak

    return audio.astype(np.float32, copy=False)


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
    logger.warning("Qwen3-ASR output has no native timestamps; fallback token timestamps were generated.")
    return " ".join(tokens), timestamps


def parse_qwen_asr_output(raw_output: str, audio_duration_ms: int) -> tuple[str, list[list[int]]]:
    """解析 Qwen3-ASR 输出为项目标准字段。

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


class QwenASREngine:
    """Qwen3-ASR 推理引擎。

    Args:
        model_path: 本地模型目录路径。
        device: 推理设备，支持 `cpu` 或 `cuda`。
    """

    def __init__(self, model_path: str, device: str = "cpu") -> None:
        """初始化 Qwen3-ASR 推理引擎。

        Args:
            model_path: 本地模型目录路径。
            device: 推理设备。

        Returns:
            None.

        Raises:
            RuntimeError: 模型或依赖加载失败时抛出。
        """
        self.model_path = _resolve_model_path(model_path)
        self.device = _normalize_device(device)
        self.sample_rate = 16000
        self.max_new_tokens = 1024
        self._lock = Lock()
        self._torch = _import_torch()

        try:
            from transformers import AutoModel, AutoProcessor
        except ImportError as exc:
            raise RuntimeError("Qwen3-ASR requires transformers to be installed.") from exc

        try:
            self._processor = AutoProcessor.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                fix_mistral_regex=True,
            )
        except TypeError:
            self._processor = AutoProcessor.from_pretrained(self.model_path, trust_remote_code=True)

        torch_dtype = self._torch.float32
        if self.device == "cuda":
            torch_dtype = self._torch.bfloat16 if self._torch.cuda.is_bf16_supported() else self._torch.float16

        self._model = AutoModel.from_pretrained(
            self.model_path,
            trust_remote_code=True,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
        )
        self._model = self._model.to(self.device)
        self._model.eval()
        self._model_device = next(self._model.parameters()).device
        self._model_dtype = next(self._model.parameters()).dtype

    def _build_prompt(self) -> str:
        """构造单条音频请求的 chat template。

        Args:
            None.

        Returns:
            str: 供 processor 编码的文本提示。

        Raises:
            RuntimeError: chat template 构造失败时抛出。
        """
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": [{"type": "audio", "audio": ""}]},
        ]

        try:
            return str(self._processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False))
        except Exception as exc:
            raise RuntimeError("Failed to build Qwen3-ASR prompt with chat template.") from exc

    def _generate(self, waveform: np.ndarray) -> str:
        """执行一次模型生成。

        Args:
            waveform: 单声道 16k float32 音频数组。

        Returns:
            str: 模型解码后的文本。

        Raises:
            RuntimeError: 推理失败时抛出。
        """
        prompt = self._build_prompt()

        with self._lock:
            try:
                inputs = self._processor(
                    text=[prompt],
                    audio=[waveform],
                    return_tensors="pt",
                    padding=True,
                )
                inputs = inputs.to(self._model_device).to(self._model_dtype)
                generated = self._model.generate(**inputs, max_new_tokens=self.max_new_tokens)
                sequences = generated.sequences if hasattr(generated, "sequences") else generated
                prompt_length = int(inputs["input_ids"].shape[1])
                decoded = self._processor.batch_decode(
                    sequences[:, prompt_length:],
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=False,
                )
            except Exception as exc:
                raise RuntimeError("Qwen3-ASR generation failed.") from exc

        return str(decoded[0]).strip() if decoded else ""

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

        try:
            waveform = _load_audio(audio_path, self.sample_rate)
            audio_duration_ms = int(round(len(waveform) / self.sample_rate * 1000))
            raw_output = self._generate(waveform)
            text, timestamps = parse_qwen_asr_output(raw_output, audio_duration_ms=audio_duration_ms)
            return {
                "key": audio_path.stem,
                "text": text,
                "timestamp": timestamps,
            }
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to transcribe audio with Qwen3-ASR: {audio_path}") from exc


def load_qwen_asr(model_path: str, device: str) -> QwenASREngine:
    """加载或返回缓存的 Qwen3-ASR 引擎。

    Args:
        model_path: 本地模型目录路径。
        device: 推理设备。

    Returns:
        QwenASREngine: 已初始化的引擎实例。

    Raises:
        RuntimeError: 引擎初始化失败时抛出。
    """
    resolved_model_path = _resolve_model_path(model_path)
    normalized_device = _normalize_device(device)
    cache_key = (resolved_model_path, normalized_device)
    engine = _qwen_asr_engines.get(cache_key)
    if engine is None:
        engine = QwenASREngine(model_path=resolved_model_path, device=normalized_device)
        _qwen_asr_engines[cache_key] = engine
    return engine


def get_qwen_asr(model_path: str, device: str) -> QwenASREngine:
    """获取已加载的 Qwen3-ASR 引擎。

    Args:
        model_path: 本地模型目录路径。
        device: 推理设备。

    Returns:
        QwenASREngine: 已初始化的引擎实例。

    Raises:
        RuntimeError: 指定引擎尚未加载时抛出。
    """
    resolved_model_path = _resolve_model_path(model_path)
    normalized_device = _normalize_device(device)
    cache_key = (resolved_model_path, normalized_device)
    engine = _qwen_asr_engines.get(cache_key)
    if engine is None:
        raise RuntimeError(
            f"Qwen3-ASR engine is not loaded: model_path={resolved_model_path}, device={normalized_device}."
        )
    return engine


def reset_qwen_asr_engine(model_path: str | None = None, device: str | None = None) -> None:
    """重置 Qwen3-ASR 引擎缓存。

    Args:
        model_path: 指定模型路径；为 `None` 时清空全部缓存。
        device: 指定设备；仅在 `model_path` 也提供时生效。

    Returns:
        None.

    Raises:
        None.
    """
    if model_path is None:
        _qwen_asr_engines.clear()
    else:
        resolved_model_path = _resolve_model_path(model_path)
        normalized_device = _normalize_device(device or "cpu")
        _qwen_asr_engines.pop((resolved_model_path, normalized_device), None)

    gc.collect()

    try:
        torch = _import_torch()
    except RuntimeError:
        return

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
