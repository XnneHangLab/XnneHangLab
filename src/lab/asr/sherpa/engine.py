from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING, Any

from lab.asr.sherpa.utils import (
    assert_file_exists,
    build_asr_response,
    collect_vad_timestamps,
    create_vad_config,
    decode_audio,
    find_first_existing,
    import_sherpa_onnx,
)
from lab.utils.FFmpegHelper import get_audio_duration

if TYPE_CHECKING:
    from pathlib import Path

    import numpy.typing as npt

    from lab.asr.types import ASRResponse, VadResponse

    Float32Array = npt.NDArray[Any]

_asr_engine: SherpaASREngine | None = None
_vad_engine: SherpaVADEngine | None = None


class SherpaASREngine:
    """sherpa-onnx paraformer 推理引擎（全局单例）。

    Args:
        model_dir: paraformer 模型目录路径。
        num_threads: 推理线程数，默认 2。
    """

    def __init__(self, model_dir: Path, num_threads: int = 2) -> None:
        self.model_dir = model_dir
        self.num_threads = num_threads
        self.sample_rate = 16000
        self._lock = Lock()

        assert_file_exists(self.model_dir, "model directory")

        self._sherpa_onnx = import_sherpa_onnx()
        self._is_streaming_model = (
            find_first_existing(self.model_dir, ["encoder.int8.onnx", "encoder.onnx"]) is not None
            and find_first_existing(self.model_dir, ["decoder.int8.onnx", "decoder.onnx"]) is not None
        )
        self._recognizer = self._create_recognizer()

    def _create_recognizer(self) -> Any:
        """创建并缓存 sherpa-onnx 识别器实例。

        Args:
            None.

        Returns:
            Any: sherpa-onnx 识别器实例。

        Raises:
            FileNotFoundError: 模型目录缺少必要文件时抛出。
        """
        tokens = find_first_existing(self.model_dir, ["tokens.txt"])
        if tokens is None:
            raise FileNotFoundError(f"tokens.txt not found in model directory: {self.model_dir}")

        if self._is_streaming_model:
            encoder = find_first_existing(self.model_dir, ["encoder.int8.onnx", "encoder.onnx"])
            decoder = find_first_existing(self.model_dir, ["decoder.int8.onnx", "decoder.onnx"])
            if encoder is None or decoder is None:
                raise FileNotFoundError(
                    "streaming paraformer model files not found. Expected encoder*.onnx and decoder*.onnx"
                )

            return self._sherpa_onnx.OnlineRecognizer.from_paraformer(
                tokens=str(tokens),
                encoder=str(encoder),
                decoder=str(decoder),
                num_threads=self.num_threads,
                provider="cpu",
                sample_rate=self.sample_rate,
                feature_dim=80,
                decoding_method="greedy_search",
            )

        paraformer = find_first_existing(self.model_dir, ["model.int8.onnx", "model.onnx"])
        if paraformer is None:
            raise FileNotFoundError("offline paraformer model files not found. Expected model*.onnx")

        return self._sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=str(paraformer),
            tokens=str(tokens),
            num_threads=self.num_threads,
            sample_rate=self.sample_rate,
            feature_dim=80,
            decoding_method="greedy_search",
            debug=False,
        )

    def transcribe(self, audio_path: Path) -> ASRResponse:
        """对音频执行 ASR 推理，返回兼容 funasr 格式的结果。

        text 格式为字符间空格分隔（如 `那 年 长 街`），
        timestamp 单位为毫秒，与 ASRResponse 规范一致。

        Args:
            audio_path: 输入音频文件路径（支持 wav/opus/mp3 等）。

        Returns:
            ASRResponse: 包含 key、text、timestamp 的识别结果。

        Raises:
            FileNotFoundError: 音频文件不存在时抛出。
            RuntimeError: 推理失败时抛出。
        """
        assert_file_exists(audio_path, "audio file")

        try:
            samples, sample_rate = decode_audio(audio_path, sample_rate=self.sample_rate)
            result = self._transcribe_samples(samples, sample_rate)
            return build_asr_response(audio_path, result)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to transcribe audio with sherpa-onnx: {audio_path}") from exc

    def _transcribe_samples(self, samples: Float32Array, sample_rate: int) -> Any:
        """执行一次底层 sherpa-onnx 推理。

        Args:
            samples: 解码后的单声道浮点音频数据。
            sample_rate: 音频采样率。

        Returns:
            Any: sherpa-onnx 原始识别结果对象。

        Raises:
            RuntimeError: 解码过程中出现底层异常时抛出。
        """
        with self._lock:
            stream = self._recognizer.create_stream()

            if self._is_streaming_model:
                stream.accept_waveform(sample_rate, samples)
                stream.accept_waveform(sample_rate, [0.0] * int(0.66 * sample_rate))
                stream.input_finished()

                while self._recognizer.is_ready(stream):
                    self._recognizer.decode_stream(stream)
                return self._recognizer.get_result(stream)

            stream.accept_waveform(sample_rate, samples)
            self._recognizer.decode_stream(stream)
            return stream.result


class SherpaVADEngine:
    """sherpa-onnx silero-vad 推理引擎（全局单例）。

    Args:
        vad_model_path: silero_vad.onnx 文件路径。
        sample_rate: 音频采样率，默认 16000。
    """

    def __init__(self, vad_model_path: Path, sample_rate: int = 16000) -> None:
        self.vad_model_path = vad_model_path
        self.sample_rate = sample_rate
        self._lock = Lock()

        assert_file_exists(self.vad_model_path, "vad model")

        self._sherpa_onnx = import_sherpa_onnx()
        self._config = self._create_config()
        self._window_size = self._config.silero_vad.window_size

    def _create_config(self) -> Any:
        """创建 silero-vad 配置对象。

        Args:
            None.

        Returns:
            Any: sherpa-onnx VAD 配置对象。

        Raises:
            None.
        """
        return create_vad_config(self._sherpa_onnx, self.vad_model_path, self.sample_rate)

    def detect(self, audio_path: Path) -> VadResponse:
        """对音频执行 VAD 检测，返回语音活动时间段。

        Args:
            audio_path: 输入音频文件路径。

        Returns:
            VadResponse: 包含 key、timestamp、audio_length 的检测结果。
            timestamp 单位为毫秒，格式为 `[[start, end], ...]`。

        Raises:
            FileNotFoundError: 音频文件不存在时抛出。
        """
        assert_file_exists(audio_path, "audio file")

        samples, sample_rate = decode_audio(audio_path, sample_rate=self.sample_rate)
        timestamps = self._detect_timestamps(samples, sample_rate)

        response: VadResponse = {
            "key": audio_path.stem,
            "timestamp": timestamps,
            "audio_length": get_audio_duration(audio_path),
        }
        return response

    def _detect_timestamps(self, samples: Float32Array, sample_rate: int) -> list[list[int]]:
        """执行一次底层 sherpa-onnx VAD 推理。

        Args:
            samples: 解码后的单声道浮点音频数据。
            sample_rate: 音频采样率。

        Returns:
            list[list[int]]: 以毫秒表示的语音段列表。

        Raises:
            None.
        """
        with self._lock:
            detector = self._sherpa_onnx.VoiceActivityDetector(self._config, buffer_size_in_seconds=30)
            return collect_vad_timestamps(detector, samples, sample_rate, self._window_size)


def load_sherpa_asr(model_dir: Path, num_threads: int = 2) -> SherpaASREngine:
    """加载或返回已缓存的 ASR 引擎单例。

    Args:
        model_dir: paraformer 模型目录路径。
        num_threads: 推理线程数，默认 2。

    Returns:
        SherpaASREngine: 已初始化的 ASR 引擎实例。

    Raises:
        FileNotFoundError: 模型目录不存在或缺少必要文件时抛出。
    """
    global _asr_engine
    if _asr_engine is None:
        _asr_engine = SherpaASREngine(model_dir=model_dir, num_threads=num_threads)
    return _asr_engine


def load_sherpa_vad(vad_model_path: Path) -> SherpaVADEngine:
    """加载或返回已缓存的 VAD 引擎单例。

    Args:
        vad_model_path: silero-vad 模型路径。

    Returns:
        SherpaVADEngine: 已初始化的 VAD 引擎实例。

    Raises:
        FileNotFoundError: VAD 模型文件不存在时抛出。
    """
    global _vad_engine
    if _vad_engine is None:
        _vad_engine = SherpaVADEngine(vad_model_path=vad_model_path)
    return _vad_engine


def get_sherpa_asr() -> SherpaASREngine:
    """获取已加载的 ASR 引擎，未初始化时抛出异常。

    Args:
        None.

    Returns:
        SherpaASREngine: 已初始化的 ASR 引擎实例。

    Raises:
        RuntimeError: ASR 引擎尚未初始化时抛出。
    """
    if _asr_engine is None:
        raise RuntimeError("Sherpa ASR engine is not loaded. Call load_sherpa_asr() first.")
    return _asr_engine


def get_sherpa_vad() -> SherpaVADEngine:
    """获取已加载的 VAD 引擎，未初始化时抛出异常。

    Args:
        None.

    Returns:
        SherpaVADEngine: 已初始化的 VAD 引擎实例。

    Raises:
        RuntimeError: VAD 引擎尚未初始化时抛出。
    """
    if _vad_engine is None:
        raise RuntimeError("Sherpa VAD engine is not loaded. Call load_sherpa_vad() first.")
    return _vad_engine


def reset_sherpa_engines() -> None:
    """重置已缓存的 sherpa-onnx 引擎单例。

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    global _asr_engine, _vad_engine
    _asr_engine = None
    _vad_engine = None
