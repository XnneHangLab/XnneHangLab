"""sherpa-onnx paraformer 输出格式探索脚本。

用途：验证 sherpa-onnx 的输出是否兼容 ASRResponse 和 VadResponse，
以及 convert_asr_response_to_sentences 是否能正常工作。

依赖安装：
uv sync --group sherpa-onnx
# 或
uv add --group sherpa-onnx sherpa-onnx

模型下载（选其一）：
# paraformer-zh streaming（推荐，支持实时）
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2
tar xf sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2 -C ./models/

# silero-vad（VAD 用）
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx -P ./models/
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt
from loguru import logger

from lab.asr.converter import convert_asr_response_to_sentences
from lab.asr.sherpa.utils import (
    assert_file_exists,
    build_asr_response,
    collect_vad_timestamps,
    create_vad_config,
    decode_audio,
    find_first_existing,
    import_sherpa_onnx,
)
from lab.logger.logger_group import init_logger
from lab.utils.FFmpegHelper import get_audio_duration

if TYPE_CHECKING:
    from lab.asr.types import VadResponse

DEFAULT_OFFLINE_MODEL_DIR = Path("./models/sherpa-onnx-paraformer-zh-2023-09-14")
logger = logger.bind(group="asr")
Float32Array = npt.NDArray[np.float32]


def _log_timing(stage: str, import_s: float, model_load_s: float, inference_s: float) -> None:
    logger.info(
        f"{stage} timing import={import_s:.3f}s model_load={model_load_s:.3f}s inference={inference_s:.3f}s",
    )


def _decode_online_paraformer(samples: Float32Array, sample_rate: int, model_dir: Path) -> Any:
    tokens = find_first_existing(model_dir, ["tokens.txt"])
    encoder = find_first_existing(model_dir, ["encoder.int8.onnx", "encoder.onnx"])
    decoder = find_first_existing(model_dir, ["decoder.int8.onnx", "decoder.onnx"])

    if tokens is None or encoder is None or decoder is None:
        raise FileNotFoundError(
            "streaming paraformer model files not found. Expected tokens.txt, encoder*.onnx, decoder*.onnx",
        )

    import_started_at = time.perf_counter()
    sherpa_onnx = import_sherpa_onnx()
    import_elapsed = time.perf_counter() - import_started_at

    load_started_at = time.perf_counter()
    recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
        tokens=str(tokens),
        encoder=str(encoder),
        decoder=str(decoder),
        num_threads=1,
        provider="cpu",
        sample_rate=sample_rate,
        feature_dim=80,
        decoding_method="greedy_search",
    )
    load_elapsed = time.perf_counter() - load_started_at

    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    stream.accept_waveform(sample_rate, np.zeros(int(0.66 * sample_rate), dtype=np.float32))
    stream.input_finished()

    inference_started_at = time.perf_counter()
    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)
    inference_elapsed = time.perf_counter() - inference_started_at

    _log_timing("asr", import_elapsed, load_elapsed, inference_elapsed)

    return recognizer.get_result(stream)


def _decode_offline_paraformer(samples: Float32Array, sample_rate: int, model_dir: Path) -> Any:
    tokens = find_first_existing(model_dir, ["tokens.txt"])
    paraformer = find_first_existing(model_dir, ["model.int8.onnx", "model.onnx"])

    if tokens is None or paraformer is None:
        raise FileNotFoundError("offline paraformer model files not found. Expected tokens.txt and model*.onnx")

    import_started_at = time.perf_counter()
    sherpa_onnx = import_sherpa_onnx()
    import_elapsed = time.perf_counter() - import_started_at

    load_started_at = time.perf_counter()
    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(paraformer),
        tokens=str(tokens),
        num_threads=1,
        sample_rate=sample_rate,
        feature_dim=80,
        decoding_method="greedy_search",
        debug=False,
    )
    load_elapsed = time.perf_counter() - load_started_at

    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)

    inference_started_at = time.perf_counter()
    recognizer.decode_stream(stream)
    inference_elapsed = time.perf_counter() - inference_started_at

    _log_timing("asr", import_elapsed, load_elapsed, inference_elapsed)

    return stream.result


def probe_asr(audio_path: Path, model_dir: Path) -> None:
    """探索 sherpa-onnx paraformer 的原始输出格式。

    打印原始输出，然后尝试构造 ASRResponse 并跑
    convert_asr_response_to_sentences，验证兼容性。

    Args:
        audio_path: 输入音频文件路径。
        model_dir: sherpa-onnx paraformer 模型目录。

    Returns:
        None.

    Raises:
        ImportError: sherpa-onnx 未安装时抛出。
        FileNotFoundError: 模型或音频文件不存在时抛出。
    """

    try:
        import_started_at = time.perf_counter()
        import_sherpa_onnx()
        logger.info(f"asr import_check import={time.perf_counter() - import_started_at:.3f}s")
    except ImportError as exc:
        raise ImportError("sherpa-onnx is required. Install it with `uv add sherpa-onnx`.") from exc

    assert_file_exists(audio_path, "audio file")
    assert_file_exists(model_dir, "model directory")

    samples, sample_rate = decode_audio(audio_path)

    is_streaming_model = (
        find_first_existing(model_dir, ["encoder.int8.onnx", "encoder.onnx"]) is not None
        and find_first_existing(model_dir, ["decoder.int8.onnx", "decoder.onnx"]) is not None
    )

    if is_streaming_model:
        logger.warning(
            "warning: streaming paraformer is designed for real-time chunked input; "
            "offline accuracy validation should use an offline paraformer model instead.",
        )

    result = (
        _decode_online_paraformer(samples, sample_rate, model_dir)
        if is_streaming_model
        else _decode_offline_paraformer(samples, sample_rate, model_dir)
    )

    response = build_asr_response(audio_path, result)
    logger.info(
        "asr result "
        f"text_len={len(response['text'])} token_count={len(getattr(result, 'tokens', []))} "
        f"timestamp_count={len(response['timestamp'])}",
    )
    logger.info(f"constructed ASRResponse: {response}")

    compatibility = len(response["text"].split()) == len(response["timestamp"])
    logger.info(f"asr token_timestamp_aligned={compatibility}")

    try:
        sentences = convert_asr_response_to_sentences(response)
        logger.info(f"converted sentences: {sentences}")
    except Exception as exc:
        logger.exception(f"convert_asr_response_to_sentences failed: {exc!r}")


def probe_vad(audio_path: Path, vad_model_path: Path) -> None:
    """探索 sherpa-onnx silero-vad 的原始输出格式。

    打印原始输出，然后尝试构造 VadResponse，验证兼容性。

    Args:
        audio_path: 输入音频文件路径。
        vad_model_path: silero_vad.onnx 文件路径。

    Returns:
        None.

    Raises:
        ImportError: sherpa-onnx 未安装时抛出。
        FileNotFoundError: 模型或音频文件不存在时抛出。
    """

    try:
        import_started_at = time.perf_counter()
        sherpa_onnx = import_sherpa_onnx()
        import_elapsed = time.perf_counter() - import_started_at
    except ImportError as exc:
        raise ImportError("sherpa-onnx is required. Install it with `uv add sherpa-onnx`.") from exc

    assert_file_exists(audio_path, "audio file")
    assert_file_exists(vad_model_path, "vad model")

    samples, sample_rate = decode_audio(audio_path)

    config = create_vad_config(sherpa_onnx, vad_model_path, sample_rate)
    window_size = config.silero_vad.window_size
    load_started_at = time.perf_counter()
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
    load_elapsed = time.perf_counter() - load_started_at

    inference_started_at = time.perf_counter()
    timestamps = collect_vad_timestamps(vad, samples, sample_rate, window_size)
    inference_elapsed = time.perf_counter() - inference_started_at

    _log_timing("vad", import_elapsed, load_elapsed, inference_elapsed)

    logger.info(f"vad segment_count={len(timestamps)}")

    response: VadResponse = {
        "key": audio_path.stem,
        "timestamp": timestamps,
        "audio_length": get_audio_duration(audio_path),
    }
    logger.info(f"constructed VadResponse: {response}")


if __name__ == "__main__":
    init_logger()
    parser = argparse.ArgumentParser(description="sherpa-onnx 兼容性探索")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=DEFAULT_OFFLINE_MODEL_DIR,
    )
    parser.add_argument("--vad-model", type=Path, default=Path("./models/silero_vad.onnx"))
    parser.add_argument("--skip-vad", action="store_true")
    args = parser.parse_args()

    probe_asr(args.audio, args.model_dir)
    if not args.skip_vad:
        probe_vad(args.audio, args.vad_model)
