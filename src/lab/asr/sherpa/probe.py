"""sherpa-onnx paraformer 输出格式探索脚本。

用途：验证 sherpa-onnx 的输出是否兼容 ASRResponse 和 VadResponse，
以及 convert_asr_response_to_sentences 是否能正常工作。

依赖安装：
uv add sherpa-onnx

模型下载（选其一）：
# paraformer-zh streaming（推荐，支持实时）
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2
tar xf sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2 -C ./models/

# silero-vad（VAD 用）
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx -P ./models/
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from lab.asr.funasr.converter import convert_asr_response_to_sentences
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.utils.FFmpegHelper import get_audio_duration

if TYPE_CHECKING:
    from lab.asr.types import ASRResponse, VadResponse


def _get_ffmpeg_path() -> str:
    try:
        settings = load_settings_file("lab.toml", XnneHangLabSettings)
    except Exception:
        return "ffmpeg"
    return settings.asr.FFMPEG_PATH


def _assert_file_exists(path: Path, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")


def _find_first_existing(model_dir: Path, filenames: list[str]) -> Path | None:
    for filename in filenames:
        candidate = model_dir / filename
        if candidate.exists():
            return candidate
    return None


def _decode_audio(audio_path: Path, sample_rate: int = 16000) -> tuple[np.ndarray, int]:
    command = [
        _get_ffmpeg_path(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="ignore").strip() or "ffmpeg decode failed")

    samples = np.frombuffer(result.stdout, dtype=np.float32)
    if samples.size == 0:
        raise RuntimeError(f"Decoded audio is empty: {audio_path}")

    return np.ascontiguousarray(samples), sample_rate


def _decode_online_paraformer(samples: np.ndarray, sample_rate: int, model_dir: Path) -> Any:
    import sherpa_onnx

    tokens = _find_first_existing(model_dir, ["tokens.txt"])
    encoder = _find_first_existing(model_dir, ["encoder.int8.onnx", "encoder.onnx"])
    decoder = _find_first_existing(model_dir, ["decoder.int8.onnx", "decoder.onnx"])

    if tokens is None or encoder is None or decoder is None:
        raise FileNotFoundError(
            "streaming paraformer model files not found. Expected tokens.txt, encoder*.onnx, decoder*.onnx",
        )

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

    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    stream.accept_waveform(sample_rate, np.zeros(int(0.66 * sample_rate), dtype=np.float32))
    stream.input_finished()

    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)

    return recognizer.get_result(stream)


def _decode_offline_paraformer(samples: np.ndarray, sample_rate: int, model_dir: Path) -> Any:
    import sherpa_onnx

    tokens = _find_first_existing(model_dir, ["tokens.txt"])
    paraformer = _find_first_existing(model_dir, ["model.int8.onnx", "model.onnx"])

    if tokens is None or paraformer is None:
        raise FileNotFoundError("offline paraformer model files not found. Expected tokens.txt and model*.onnx")

    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(paraformer),
        tokens=str(tokens),
        num_threads=1,
        sample_rate=sample_rate,
        feature_dim=80,
        decoding_method="greedy_search",
        debug=False,
    )

    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    recognizer.decode_stream(stream)
    return stream.result


def _build_asr_response(audio_path: Path, result: Any) -> ASRResponse:
    tokens: list[str] = list(getattr(result, "tokens", []))
    timestamps: list[float] = list(getattr(result, "timestamps", []))
    text = getattr(result, "text", "") or "".join(tokens)

    response: ASRResponse = {
        "key": audio_path.stem,
        "text": text,
        "timestamp": [[int(t * 1000), int(t * 1000) + 240] for t in timestamps],
    }
    return response


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
        import sherpa_onnx
    except ImportError as exc:
        raise ImportError("sherpa-onnx is required. Install it with `uv add sherpa-onnx`.") from exc

    _assert_file_exists(audio_path, "audio file")
    _assert_file_exists(model_dir, "model directory")

    samples, sample_rate = _decode_audio(audio_path)

    is_streaming_model = (
        _find_first_existing(model_dir, ["encoder.int8.onnx", "encoder.onnx"]) is not None
        and _find_first_existing(model_dir, ["decoder.int8.onnx", "decoder.onnx"]) is not None
    )

    result = (
        _decode_online_paraformer(samples, sample_rate, model_dir)
        if is_streaming_model
        else _decode_offline_paraformer(samples, sample_rate, model_dir)
    )

    print("raw output:", result)
    print("result.tokens type:", type(getattr(result, "tokens", None)))
    print("result.tokens length:", len(getattr(result, "tokens", [])))
    print("result.timestamps type:", type(getattr(result, "timestamps", None)))
    print("result.timestamps length:", len(getattr(result, "timestamps", [])))

    response = _build_asr_response(audio_path, result)
    print("constructed ASRResponse:", response)

    compatibility = len(response["text"].split()) == len(response["timestamp"])
    print("len(response['text'].split()) == len(response['timestamp']):", compatibility)

    try:
        sentences = convert_asr_response_to_sentences(response)
        print("converted sentences:", sentences)
    except Exception as exc:
        print("convert_asr_response_to_sentences failed:", repr(exc))


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
        import sherpa_onnx
    except ImportError as exc:
        raise ImportError("sherpa-onnx is required. Install it with `uv add sherpa-onnx`.") from exc

    _assert_file_exists(audio_path, "audio file")
    _assert_file_exists(vad_model_path, "vad model")

    samples, sample_rate = _decode_audio(audio_path)

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(vad_model_path)
    config.silero_vad.threshold = 0.5
    config.silero_vad.min_silence_duration = 0.25
    config.silero_vad.min_speech_duration = 0.25
    config.silero_vad.max_speech_duration = 8
    config.sample_rate = sample_rate

    window_size = config.silero_vad.window_size
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)

    offset = 0
    segments: list[dict[str, int]] = []
    timestamps: list[list[int]] = []

    while offset + window_size <= len(samples):
        vad.accept_waveform(samples[offset : offset + window_size])
        offset += window_size

        while not vad.empty():
            segment = vad.front
            start_sample = int(segment.start)
            num_samples = len(segment.samples)
            end_sample = start_sample + num_samples

            segments.append({"start": start_sample, "end": end_sample, "num_samples": num_samples})
            timestamps.append([int(start_sample * 1000 / sample_rate), int(end_sample * 1000 / sample_rate)])
            vad.pop()

    if offset < len(samples):
        vad.accept_waveform(samples[offset:])

    vad.flush()

    while not vad.empty():
        segment = vad.front
        start_sample = int(segment.start)
        num_samples = len(segment.samples)
        end_sample = start_sample + num_samples

        segments.append({"start": start_sample, "end": end_sample, "num_samples": num_samples})
        timestamps.append([int(start_sample * 1000 / sample_rate), int(end_sample * 1000 / sample_rate)])
        vad.pop()

    print("raw segments:", segments)

    response: VadResponse = {
        "key": audio_path.stem,
        "timestamp": timestamps,
        "audio_length": get_audio_duration(audio_path),
    }
    print("constructed VadResponse:", response)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="sherpa-onnx 兼容性探索")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("./models/sherpa-onnx-streaming-paraformer-bilingual-zh-en"),
    )
    parser.add_argument("--vad-model", type=Path, default=Path("./models/silero_vad.onnx"))
    parser.add_argument("--skip-vad", action="store_true")
    args = parser.parse_args()

    probe_asr(args.audio, args.model_dir)
    if not args.skip_vad:
        probe_vad(args.audio, args.vad_model)
