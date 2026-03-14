from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp

from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse
from lab.asr.converter import convert_asr_response_to_sentences
from lab.asr.types import ASRResponse, Sentence
from lab.logger.logger_group import logger

if TYPE_CHECKING:
    from pathlib import Path

_asr_logger = logger.bind(group="asr")


class ASRRequest(BaseRequest):
    file_path: Path
    only_text: bool = False


class ASRResponseModel(BaseResponse):
    key: str
    text: str
    timestamp: list[list[int]]

    def to_dict(self) -> ASRResponse:
        """将响应模型转换为标准 ASRResponse。

        Args:
            None.

        Returns:
            ASRResponse: 标准化后的 ASR 响应。

        Raises:
            None.
        """
        return ASRResponse(
            key=self.key,
            text=self.text,
            timestamp=self.timestamp,
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
        self.base_url = self.base_url + "/asr/funasr/transcribe"
        self.last_error: str | None = None

    def post(self, request: ASRRequest) -> list[Sentence] | None:  # type: ignore[override]
        """调用统一 ASR 接口并转换为句子列表。

        Args:
            request: 包含待识别音频路径的请求对象。

        Returns:
            list[Sentence] | None: 成功时返回句子列表，失败时返回 None。

        Raises:
            None.
        """
        if not request.file_path.exists():
            self.last_error = f"File not found: {request.file_path}"
            _asr_logger.error(self.last_error)
            return None

        self.last_error = None

        try:
            with request.file_path.open("rb") as file:
                response = self.session.post(self.base_url, files={"file": file})
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            self.last_error = f"ASR request failed: {exc}"
            _asr_logger.error(self.last_error)
            return None

        if payload.get("code") not in (None, 200, "200"):
            self.last_error = str(payload.get("message", "ASR request failed"))
            _asr_logger.error(f"ASR server returned error payload: {payload}")
            return None

        try:
            asr_response: ASRResponse = ASRResponseModel.model_validate(payload).to_dict()
            sentences = convert_asr_response_to_sentences(asr_response)
            if not sentences:
                self.last_error = "ASR returned no sentences."
                _asr_logger.error(f"ASR returned no sentences: {payload}")
                return None
            return sentences
        except Exception as exc:
            self.last_error = f"Failed to parse ASR response: {exc}"
            _asr_logger.error(f"Failed to parse ASR response: {exc}, {payload}")
            return None

    async def asyncpost(self, request: ASRRequest) -> ASRResponse | None:  # type: ignore[override]
        """异步调用统一 ASR 接口。

        Args:
            request: 包含待识别音频路径的请求对象。

        Returns:
            ASRResponse | None: 成功时返回标准 ASR 响应，失败时返回 None。

        Raises:
            None.
        """
        self.async_session = await self.get_async_session()
        if not request.file_path.exists():
            self.last_error = f"File not found: {request.file_path}"
            _asr_logger.error(self.last_error)
            return None

        try:
            with request.file_path.open("rb") as file:
                form = aiohttp.FormData()
                form.add_field("file", file, filename=request.file_path.name)
                async with self.async_session.post(self.base_url, data=form) as response:
                    if response.status != 200:
                        self.last_error = f"Failed to get a valid response: {response.status}"
                        _asr_logger.error(self.last_error)
                        return None

                    payload = await response.json()
        except Exception as exc:
            self.last_error = f"ASR request failed: {exc}"
            _asr_logger.error(self.last_error)
            return None
        finally:
            await self.async_session.close()

        try:
            return ASRResponseModel.model_validate(payload).to_dict()
        except Exception as exc:
            self.last_error = f"Failed to parse ASR response: {exc}"
            _asr_logger.error(f"Failed to parse ASR response: {exc}, {payload}")
            return None
