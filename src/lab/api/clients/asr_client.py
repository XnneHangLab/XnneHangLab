from __future__ import annotations

from pathlib import Path  # noqa: TC003

from loguru import logger

from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse
from lab.asr.converter import convert_asr_response_to_sentences
from lab.asr.types import ASRResponse, Sentence, WhisperResponse, WhisperSegment
from lab.asr.whisper.converter import convert_whisper_response_to_sentences
from lab.config_manager import XnneHangLabSettings, load_settings_file


class ASRRequest(BaseRequest):
    file_path: Path
    only_text: bool = False


class ASRResponseModel(BaseResponse):
    key: str
    text: str
    timestamp: list[list[int]]

    def to_dict(self) -> ASRResponse:
        """将响应模型转换为 ASRResponse。

        Args:
            None.

        Returns:
            ASRResponse: 标准化的 ASR 响应字典。

        Raises:
            None.
        """
        return ASRResponse(
            key=self.key,
            text=self.text,
            timestamp=self.timestamp,
        )


class WhisperASRResponseModel(BaseResponse):
    segments: list[WhisperSegment]
    text: str

    def to_dict(self) -> WhisperResponse:
        """将响应模型转换为 WhisperResponse。

        Args:
            None.

        Returns:
            WhisperResponse: 标准化的 Whisper 响应字典。

        Raises:
            None.
        """
        return WhisperResponse(
            text=self.text,
            segments=self.segments,
        )


class ASRClient(BaseClientInterface):
    def __init__(self) -> None:
        """初始化 ASR HTTP 客户端。

        Args:
            None.

        Returns:
            None.

        Raises:
            None.
        """
        lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.config = lab_settings.asr
        if lab_settings.asr.asr_model_provider == "sherpa":
            self.base_url = self.base_url + "/asr/funasr/transcribe"
        else:
            self.base_url = self.base_url + "/asr/whisper"

    def post(self, request: ASRRequest) -> list[Sentence] | None:  # type: ignore[override]
        """调用 ASR 接口并转换为句子列表。

        Args:
            request: 包含待识别音频路径的请求对象。

        Returns:
            list[Sentence] | None: 成功时返回句子列表，失败时返回 None。

        Raises:
            None.
        """
        if not request.file_path.exists():
            logger.error(f"File not found: {request.file_path}")
            return None

        with request.file_path.open("rb") as file:
            response = self.session.post(self.base_url, files={"file": file})
            response.raise_for_status()
            payload = response.json()

        try:
            if self.config.asr_model_provider == "sherpa":
                asr_response: ASRResponse = ASRResponseModel.model_validate(payload).to_dict()
                sentences = convert_asr_response_to_sentences(asr_response)
                if not sentences:
                    logger.error(f"ASR returned no sentences: {payload}")
                    return None
                return sentences
            if self.config.asr_model_provider == "whisper":
                whisper_response: WhisperResponse = WhisperASRResponseModel.model_validate(payload).to_dict()
                sentences = convert_whisper_response_to_sentences(whisper_response)
                if not sentences:
                    logger.error(f"Whisper returned no sentences: {payload}")
                    return None
                return sentences

            logger.error(f"Unknown ASR model provider: {self.config.asr_model_provider}")
            return None
        except Exception as exc:
            logger.error(f"Failed to parse ASR response: {exc}, {payload}")
            return None

    async def asyncpost(self, request: ASRRequest) -> ASRResponse | None:  # type: ignore[override]
        """异步调用 sherpa-onnx ASR 接口。

        Args:
            request: 包含待识别音频路径的请求对象。

        Returns:
            ASRResponse | None: 成功时返回标准 ASR 响应，失败时返回 None。

        Raises:
            None.
        """
        self.async_session = await self.get_async_session()
        if not request.file_path.exists():
            logger.error(f"File not found: {request.file_path}")
            return None

        with request.file_path.open("rb") as file:
            async with self.async_session.post(self.base_url, data={"file": file}) as response:
                if response.status != 200:
                    logger.error(f"Failed to get a valid response: {response.status}")
                    return None

                response_data = await response.json()
                try:
                    return ASRResponseModel.model_validate(response_data).to_dict()
                except Exception as exc:
                    logger.error(f"Failed to parse ASR response: {exc}, {response_data}")
                    return None
                finally:
                    await self.async_session.close()
