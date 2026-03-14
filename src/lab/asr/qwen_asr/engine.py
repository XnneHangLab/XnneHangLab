from __future__ import annotations

# pyright: reportMissingTypeArgument=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
import gc
import re
import unicodedata
from importlib import import_module
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import soundfile as sf
from loguru import logger  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

from .processor import LightProcessor

if TYPE_CHECKING:
    from collections.abc import Iterable

    from lab.asr.types import ASRResponse

logger = cast("Any", logger)

_qwen_asr_engines: dict[tuple[str, str, int], QwenASREngine] = {}
_TIMESTAMP_PATTERN = re.compile(r"<\|(\d+(?:\.\d+)?)\|>")
_TARGET_SAMPLE_RATE = 16_000
_MAX_CHUNK_MS = 30_000
_VAD_MERGE_GAP_MS = 500
_VAD_MIN_SEGMENT_MS = 1_500
_REQUIRED_MODEL_FILES = (
    "audio_encoder_model.xml",
    "thinker_embeddings_model.xml",
    "vocab.json",
    "merges.txt",
    "tokenizer_config.json",
    "prompt_template.json",
    "mel_filters.npy",
)


def _import_openvino() -> Any:
    try:
        return import_module("openvino")
    except ImportError as exc:
        raise RuntimeError(
            "Qwen3-ASR OpenVINO engine requires `openvino` to be installed. Run `uv sync` after updating dependencies."
        ) from exc


def _normalize_device(device: str) -> str:
    normalized = device.strip().upper() or "CPU"
    return normalized


def _normalize_cpu_threads(cpu_threads: int) -> int:
    if cpu_threads < 0:
        raise RuntimeError("Qwen3-ASR cpu_threads must be greater than or equal to 0.")
    return cpu_threads


def _resolve_model_path(model_path: str) -> str:
    resolved = Path(model_path).expanduser().resolve()
    if not resolved.exists():
        raise RuntimeError(
            f"Qwen3-ASR model path does not exist: {resolved}. "
            "Run `just install-qwen-asr` first or update config/lab.toml."
        )
    return str(resolved)


def _validate_model_dir(model_dir: Path) -> None:
    missing = [name for name in _REQUIRED_MODEL_FILES if not (model_dir / name).exists()]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(f"Qwen3-ASR OpenVINO model directory is incomplete: {model_dir} (missing: {missing_list})")

    has_single_decoder = (model_dir / "decoder_model.xml").exists()
    has_split_decoder = (model_dir / "decoder_prefill_kv_model.xml").exists() and (model_dir / "decoder_kv_model.xml").exists()
    if not has_single_decoder and not has_split_decoder:
        raise RuntimeError(
            "Qwen3-ASR OpenVINO model directory is incomplete: "
            f"{model_dir} (missing decoder_model.xml or decoder_prefill_kv_model.xml + decoder_kv_model.xml)"
        )


def _resample_audio(audio: np.ndarray, source_rate: int, target_rate: int = _TARGET_SAMPLE_RATE) -> np.ndarray:
    if source_rate <= 0:
        raise RuntimeError(f"Invalid source sample rate: {source_rate}")
    if len(audio) == 0:
        return np.zeros(0, dtype=np.float32)
    if source_rate == target_rate:
        return np.asarray(audio, dtype=np.float32)

    duration = len(audio) / float(source_rate)
    target_length = max(1, int(round(duration * target_rate)))
    source_positions = np.linspace(0.0, duration, num=len(audio), endpoint=False, dtype=np.float64)
    target_positions = np.linspace(0.0, duration, num=target_length, endpoint=False, dtype=np.float64)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


def _load_audio(audio_path: Path) -> tuple[np.ndarray, int]:
    try:
        waveform, sample_rate = sf.read(str(audio_path), dtype="float32", always_2d=False)
    except Exception as exc:
        raise RuntimeError(f"Failed to decode audio before Qwen3-ASR inference: {audio_path}") from exc

    audio = np.asarray(waveform, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    elif audio.ndim != 1:
        raise RuntimeError(f"Unsupported audio shape from soundfile: {audio.shape}")

    audio = _resample_audio(audio, int(sample_rate), _TARGET_SAMPLE_RATE)
    audio_duration_ms = int(round(len(audio) * 1000 / _TARGET_SAMPLE_RATE))
    return np.ascontiguousarray(audio, dtype=np.float32), audio_duration_ms


def _ms_to_sample_index(timestamp_ms: int, sample_rate: int = _TARGET_SAMPLE_RATE) -> int:
    return int(round(timestamp_ms * sample_rate / 1000))


def _expand_segments(segments: Iterable[tuple[int, int]], audio_duration_ms: int) -> list[tuple[int, int]]:
    expanded: list[tuple[int, int]] = []

    for start_ms, end_ms in segments:
        safe_start = max(0, int(start_ms))
        safe_end = min(max(safe_start, int(end_ms)), audio_duration_ms)
        if safe_end <= safe_start:
            continue

        current_start = safe_start
        while current_start < safe_end:
            current_end = min(safe_end, current_start + _MAX_CHUNK_MS)
            expanded.append((current_start, current_end))
            current_start = current_end

    return expanded


def _default_segments(audio_duration_ms: int) -> list[tuple[int, int]]:
    return _expand_segments([(0, audio_duration_ms)], audio_duration_ms)


def _merge_vad_segments(segments: list[tuple[int, int]], audio_duration_ms: int) -> list[tuple[int, int]]:
    if not segments:
        return []

    ordered = sorted(
        (
            (max(0, int(start_ms)), min(audio_duration_ms, max(int(start_ms), int(end_ms))))
            for start_ms, end_ms in segments
        ),
        key=lambda item: item[0],
    )
    merged: list[list[int]] = []

    for start_ms, end_ms in ordered:
        if end_ms <= start_ms:
            continue

        if not merged:
            merged.append([start_ms, end_ms])
            continue

        previous = merged[-1]
        gap_ms = start_ms - previous[1]
        if gap_ms <= _VAD_MERGE_GAP_MS:
            previous[1] = max(previous[1], end_ms)
            continue

        if previous[1] - previous[0] < _VAD_MIN_SEGMENT_MS:
            previous[1] = max(previous[1], end_ms)
            continue

        merged.append([start_ms, end_ms])

    if len(merged) >= 2 and merged[-1][1] - merged[-1][0] < _VAD_MIN_SEGMENT_MS:
        merged[-2][1] = merged[-1][1]
        merged.pop()

    return [(start_ms, end_ms) for start_ms, end_ms in merged]


def _ensure_sherpa_vad_loaded() -> Any:
    from lab.asr.sherpa.engine import get_sherpa_vad, load_sherpa_vad
    from lab.config_manager import XnneHangLabSettings, load_settings_file

    try:
        return get_sherpa_vad()
    except RuntimeError:
        settings = load_settings_file("lab.toml", XnneHangLabSettings)
        return load_sherpa_vad(Path(settings.asr.sherpa.vad_model_path))


def _extract_asr_text(raw_output: str) -> str:
    cleaned = raw_output.strip()
    if not cleaned:
        return ""

    if "<asr_text>" in cleaned:
        meta_part, cleaned = cleaned.split("<asr_text>", 1)
        if "language none" in meta_part.lower() and not cleaned.strip():
            return ""

    return cleaned.strip()


def _is_cjk_char(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF or 0x20000 <= code <= 0x2CEAF
    )


def _tokenize_asr_segment(segment: str) -> list[str]:
    tokens: list[str] = []
    buffer: list[str] = []

    def flush_buffer() -> None:
        if not buffer:
            return
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
    tokens = _tokenize_asr_segment(text)
    if not tokens:
        return "", []

    timestamps = _distribute_token_timestamps(tokens, 0, max(0, audio_duration_ms))
    logger.warning("Qwen3-ASR output has no native timestamps; fallback token timestamps were generated.")  # pyright: ignore[reportUnknownMemberType]
    return " ".join(tokens), timestamps


def parse_qwen_asr_output(raw_output: str, audio_duration_ms: int) -> tuple[str, list[list[int]]]:
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


def _candidate_names(port: Any) -> set[str]:
    names: set[str] = set()
    try:
        names.update(str(name) for name in port.get_names())
    except Exception:
        pass
    try:
        names.add(str(port.get_any_name()))
    except Exception:
        pass
    return {name for name in names if name}


def _resolve_input_key(compiled_model: Any, preferred_names: Iterable[str], fallback_index: int) -> str | int:
    preferred = set(preferred_names)
    inputs = list(getattr(compiled_model, "inputs", []))

    for port in inputs:
        names = _candidate_names(port)
        match = next((name for name in names if name in preferred), None)
        if match is not None:
            return match

    if 0 <= fallback_index < len(inputs):
        try:
            return str(inputs[fallback_index].get_any_name())
        except Exception:
            return fallback_index

    return fallback_index


def _first_output(outputs: Any) -> np.ndarray:
    if isinstance(outputs, dict):
        values = outputs.values()
    elif hasattr(outputs, "values"):
        values = outputs.values()
    else:
        raise RuntimeError(f"Unexpected OpenVINO output container: {type(outputs)!r}")

    first = next(iter(values), None)
    if first is None:
        raise RuntimeError("OpenVINO inference returned no outputs.")
    return np.asarray(first)


def _infer_compiled_model(compiled_model: Any, inputs: dict[str | int, np.ndarray]) -> np.ndarray:
    return _first_output(compiled_model(inputs))


def _infer_request(request: Any, inputs: dict[str | int, np.ndarray]) -> np.ndarray:
    return _first_output(request.infer(inputs))


def _infer_request_outputs(request: Any, inputs: dict[str | int, np.ndarray]) -> list[Any]:
    outputs = request.infer(inputs)
    if isinstance(outputs, dict):
        values = outputs.values()
    elif hasattr(outputs, "values"):
        values = outputs.values()
    else:
        raise RuntimeError(f"Unexpected OpenVINO output container: {type(outputs)!r}")
    return list(values)


class QwenASREngine:
    def __init__(self, model_dir: str, device: str = "CPU", cpu_threads: int = 0) -> None:
        self.model_dir = _resolve_model_path(model_dir)
        self.device = _normalize_device(device)
        self.cpu_threads = _normalize_cpu_threads(cpu_threads)
        self._lock = Lock()
        self._max_tokens = 300
        self._max_chunk_ms = _MAX_CHUNK_MS

        self._core: Any = None
        self._audio_encoder_model: Any = None
        self._thinker_embeddings_model: Any = None
        self._decoder_model: Any = None
        self._decoder_prefill_model: Any = None
        self._decoder_kv_model: Any = None
        self._decoder_request: Any = None
        self._decoder_prefill_request: Any = None
        self._decoder_kv_request: Any = None
        self._processor: LightProcessor | None = None
        self._use_split_decoder = False
        self._audio_encoder_input: str | int = 0
        self._audio_encoder_rank = 3
        self._thinker_input: str | int = 0
        self._decoder_embedding_input: str | int = 0
        self._decoder_position_input: str | int = "position_ids"
        self._decoder_prefill_embedding_input: str | int = 0
        self._decoder_prefill_position_input: str | int = 1
        self._decoder_kv_embedding_input: str | int = 0
        self._decoder_kv_position_input: str | int = 1
        self._decoder_kv_past_keys_input: str | int = 2
        self._decoder_kv_past_values_input: str | int = 3

        self._vad_engine = _ensure_sherpa_vad_loaded()
        self.load()

    def load(self) -> None:
        ov = _import_openvino()

        model_path = Path(self.model_dir)
        _validate_model_dir(model_path)

        cpu_config: dict[str, str] = {}
        if self.device == "CPU":
            cpu_config["PERFORMANCE_HINT"] = "LATENCY"
            cpu_config["ENABLE_HYPER_THREADING"] = "YES"
            if self.cpu_threads > 0:
                cpu_config["INFERENCE_NUM_THREADS"] = str(self.cpu_threads)

        self._core = ov.Core()
        self._audio_encoder_model = self._core.compile_model(
            str(model_path / "audio_encoder_model.xml"),
            self.device,
            cpu_config,
        )
        self._thinker_embeddings_model = self._core.compile_model(
            str(model_path / "thinker_embeddings_model.xml"),
            self.device,
            cpu_config,
        )
        self._processor = LightProcessor(model_path)
        self._use_split_decoder = (model_path / "decoder_prefill_kv_model.xml").exists() and (
            model_path / "decoder_kv_model.xml"
        ).exists()

        if self._use_split_decoder:
            self._decoder_prefill_model = self._core.compile_model(
                str(model_path / "decoder_prefill_kv_model.xml"),
                self.device,
                cpu_config,
            )
            self._decoder_kv_model = self._core.compile_model(
                str(model_path / "decoder_kv_model.xml"),
                self.device,
                cpu_config,
            )
            self._decoder_prefill_request = self._decoder_prefill_model.create_infer_request()
            self._decoder_kv_request = self._decoder_kv_model.create_infer_request()
        else:
            self._decoder_model = self._core.compile_model(
                str(model_path / "decoder_model.xml"),
                self.device,
                cpu_config,
            )
            self._decoder_request = self._decoder_model.create_infer_request()

        self._audio_encoder_input = _resolve_input_key(self._audio_encoder_model, ("mel",), 0)
        try:
            self._audio_encoder_rank = len(self._audio_encoder_model.inputs[0].partial_shape)
        except Exception:
            self._audio_encoder_rank = 3
        self._thinker_input = _resolve_input_key(self._thinker_embeddings_model, ("input_ids",), 0)
        if self._use_split_decoder:
            self._decoder_prefill_embedding_input = _resolve_input_key(
                self._decoder_prefill_model,
                ("inputs_embeds", "input_embeds", "hidden_states", "new_embed"),
                0,
            )
            self._decoder_prefill_position_input = _resolve_input_key(self._decoder_prefill_model, ("position_ids",), 1)
            self._decoder_kv_embedding_input = _resolve_input_key(
                self._decoder_kv_model,
                ("new_embed", "inputs_embeds", "input_embeds", "hidden_states"),
                0,
            )
            self._decoder_kv_position_input = _resolve_input_key(self._decoder_kv_model, ("new_pos", "position_ids"), 1)
            self._decoder_kv_past_keys_input = _resolve_input_key(self._decoder_kv_model, ("past_keys",), 2)
            self._decoder_kv_past_values_input = _resolve_input_key(self._decoder_kv_model, ("past_values",), 3)
        else:
            self._decoder_embedding_input = _resolve_input_key(
                self._decoder_model,
                ("inputs_embeds", "input_embeds", "hidden_states"),
                0,
            )
            self._decoder_position_input = _resolve_input_key(self._decoder_model, ("position_ids",), 1)

    def _transcribe_chunk(self, audio: np.ndarray) -> str:
        if self._processor is None:
            raise RuntimeError("Qwen3-ASR engine is not initialized.")

        with self._lock:
            mel, input_ids = self._processor.prepare(audio)
            mel_input = mel
            if self._audio_encoder_rank == 2 and mel.ndim == 3:
                mel_input = mel[0]

            audio_embeddings = _infer_compiled_model(
                self._audio_encoder_model,
                {self._audio_encoder_input: mel_input},
            )
            text_embeddings = _infer_compiled_model(
                self._thinker_embeddings_model,
                {self._thinker_input: input_ids},
            )

            combined_embeddings = np.array(text_embeddings, copy=True)
            audio_pad_mask = input_ids[0] == self._processor.pad_id
            audio_pad_indices = np.flatnonzero(audio_pad_mask)
            audio_token_count = int(audio_embeddings.shape[1])
            fill_count = min(len(audio_pad_indices), audio_token_count)
            if fill_count > 0:
                combined_embeddings[0, audio_pad_indices[:fill_count], :] = audio_embeddings[0, :fill_count, :]

            prompt_length = int(combined_embeddings.shape[1])
            position_ids = np.arange(prompt_length, dtype=np.int64)[np.newaxis, :]
            eos_id = self._processor.eos_id
            eot_id = self._processor.eot_id
            generated_ids: list[int] = []

            if self._use_split_decoder:
                if self._decoder_prefill_request is None or self._decoder_kv_request is None:
                    raise RuntimeError("Qwen3-ASR split decoder models are not initialized.")

                prefill_outputs = _infer_request_outputs(
                    self._decoder_prefill_request,
                    {
                        self._decoder_prefill_embedding_input: combined_embeddings,
                        self._decoder_prefill_position_input: position_ids,
                    },
                )
                logits = prefill_outputs[0]
                past_keys = prefill_outputs[1]
                past_values = prefill_outputs[2]
                next_token_id = int(np.argmax(logits[0, -1, :]))
                current_position = prompt_length

                while next_token_id not in {eos_id, eot_id} and len(generated_ids) < self._max_tokens:
                    generated_ids.append(next_token_id)
                    next_embedding = _infer_compiled_model(
                        self._thinker_embeddings_model,
                        {
                            self._thinker_input: np.array([[next_token_id]], dtype=np.int64),
                        },
                    )
                    decode_outputs = _infer_request_outputs(
                        self._decoder_kv_request,
                        {
                            self._decoder_kv_embedding_input: next_embedding,
                            self._decoder_kv_position_input: np.array([[current_position]], dtype=np.int64),
                            self._decoder_kv_past_keys_input: past_keys,
                            self._decoder_kv_past_values_input: past_values,
                        },
                    )
                    logits = decode_outputs[0]
                    past_keys = decode_outputs[1]
                    past_values = decode_outputs[2]
                    next_token_id = int(np.argmax(logits[0, -1, :]))
                    current_position += 1
            else:
                if self._decoder_request is None:
                    raise RuntimeError("Qwen3-ASR decoder request is not initialized.")

                self._decoder_request.reset_state()
                logits = _infer_request(
                    self._decoder_request,
                    {
                        self._decoder_embedding_input: combined_embeddings,
                        self._decoder_position_input: position_ids,
                    },
                )
                next_token_id = int(np.argmax(logits[0, -1, :]))
                current_position = prompt_length

                while next_token_id not in {eos_id, eot_id} and len(generated_ids) < self._max_tokens:
                    generated_ids.append(next_token_id)
                    next_embedding = _infer_compiled_model(
                        self._thinker_embeddings_model,
                        {
                            self._thinker_input: np.array([[next_token_id]], dtype=np.int64),
                        },
                    )
                    logits = _infer_request(
                        self._decoder_request,
                        {
                            self._decoder_embedding_input: next_embedding,
                            self._decoder_position_input: np.array([[current_position]], dtype=np.int64),
                        },
                    )
                    next_token_id = int(np.argmax(logits[0, -1, :]))
                    current_position += 1

            return self._processor.decode(generated_ids)

    def transcribe(self, audio_path: Path) -> ASRResponse:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        audio, audio_duration_ms = _load_audio(audio_path)
        segment_candidates: list[tuple[int, int]] = []

        if audio_duration_ms > self._max_chunk_ms:
            try:
                vad_result = self._vad_engine.detect(audio_path)
                vad_timestamps = cast("list[list[int]]", vad_result.get("timestamp", []))
                segment_candidates = [(int(segment[0]), int(segment[1])) for segment in vad_timestamps if len(segment) >= 2]
            except Exception:
                logger.exception(f"Qwen3-ASR VAD pre-segmentation failed for {audio_path}")  # pyright: ignore[reportUnknownMemberType]

        if segment_candidates:
            merged_segments = _merge_vad_segments(segment_candidates, audio_duration_ms)
            segments = _expand_segments(merged_segments, audio_duration_ms)
        else:
            segments = _default_segments(audio_duration_ms)

        if segments:
            preview = ", ".join(f"[{start},{end}]" for start, end in segments[:8])
            if len(segments) > 8:
                preview = f"{preview}, ..."
            logger.info(  # pyright: ignore[reportUnknownMemberType]
                f"Qwen3-ASR VAD segments for {audio_path.name}: count={len(segments)}, preview={preview}"
            )
        else:
            logger.info(f"Qwen3-ASR VAD segments for {audio_path.name}: count=0")  # pyright: ignore[reportUnknownMemberType]

        tokens: list[str] = []
        timestamps: list[list[int]] = []

        try:
            for start_ms, end_ms in segments:
                start_index = _ms_to_sample_index(start_ms)
                end_index = min(len(audio), _ms_to_sample_index(end_ms))
                if end_index <= start_index:
                    continue

                chunk = np.ascontiguousarray(audio[start_index:end_index], dtype=np.float32)
                raw_output = self._transcribe_chunk(chunk)
                chunk_text = _extract_asr_text(raw_output)
                chunk_tokens = _tokenize_asr_segment(chunk_text)
                if not chunk_tokens:
                    continue

                tokens.extend(chunk_tokens)
                timestamps.extend(_distribute_token_timestamps(chunk_tokens, start_ms, end_ms))
        except Exception as exc:
            logger.exception(f"Qwen3-ASR OpenVINO transcribe failed for {audio_path}")  # pyright: ignore[reportUnknownMemberType]
            raise RuntimeError(f"Failed to transcribe audio with Qwen3-ASR OpenVINO: {audio_path}") from exc

        text = " ".join(tokens)
        return {
            "key": audio_path.stem,
            "text": text,
            "timestamp": timestamps,
        }


def load_qwen_asr(model_path: str, device: str, cpu_threads: int = 0) -> QwenASREngine:
    resolved_model_path = _resolve_model_path(model_path)
    normalized_device = _normalize_device(device)
    normalized_cpu_threads = _normalize_cpu_threads(cpu_threads)
    cache_key = (resolved_model_path, normalized_device, normalized_cpu_threads)
    engine = _qwen_asr_engines.get(cache_key)
    if engine is None:
        engine = QwenASREngine(
            model_dir=resolved_model_path,
            device=normalized_device,
            cpu_threads=normalized_cpu_threads,
        )
        _qwen_asr_engines[cache_key] = engine
    return engine


def get_qwen_asr(model_path: str, device: str, cpu_threads: int = 0) -> QwenASREngine:
    resolved_model_path = _resolve_model_path(model_path)
    normalized_device = _normalize_device(device)
    normalized_cpu_threads = _normalize_cpu_threads(cpu_threads)
    cache_key = (resolved_model_path, normalized_device, normalized_cpu_threads)
    engine = _qwen_asr_engines.get(cache_key)
    if engine is None:
        raise RuntimeError(
            "Qwen3-ASR engine is not loaded: "
            f"model_path={resolved_model_path}, device={normalized_device}, cpu_threads={normalized_cpu_threads}."
        )
    return engine


def reset_qwen_asr_engine(model_path: str | None = None, device: str | None = None, cpu_threads: int = 0) -> None:
    if model_path is None:
        _qwen_asr_engines.clear()
    else:
        resolved_model_path = _resolve_model_path(model_path)
        normalized_device = _normalize_device(device or "CPU")
        normalized_cpu_threads = _normalize_cpu_threads(cpu_threads)
        _qwen_asr_engines.pop((resolved_model_path, normalized_device, normalized_cpu_threads), None)

    gc.collect()
