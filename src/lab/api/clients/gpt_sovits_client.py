"""GPT-SoVITS HTTP client."""

from __future__ import annotations

import base64
from pathlib import Path
from time import perf_counter
from typing import Literal, cast

from loguru import logger
from pydantic import Field

from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse
from lab.api.types import GPTSoVITSResponse


class GPTSoVITSRequest(BaseRequest):
    """GPT-SoVITS synthesis request."""

    text: str
    ref_audio_path: str | None = None
    prompt_text: str | None = None
    prompt_language: str = Field(default="auto")
    audio_type: Literal["mp3"] = Field(default="mp3")
    text_language: str = Field(default="ja")
    batch_size: int = Field(default=20)
    speed: float = Field(default=1.0)
    top_k: int = Field(default=5)
    top_p: float = Field(default=1.0)
    temperature: float = Field(default=1.0)
    repetition_penalty: float = Field(default=1.35)


class GPTSoVITSResponseModel(BaseResponse):
    """Typed GPT-SoVITS response."""

    audio_type: Literal["mp3"]
    audio_rate: int
    audio_byte: str

    def to_dict(self) -> GPTSoVITSResponse:
        return GPTSoVITSResponse(
            audio_type=self.audio_type,
            audio_rate=self.audio_rate,
            audio_byte=base64.b64decode(self.audio_byte),
        )


class GPTSoVITSClient(BaseClientInterface):
    """Client for the local GPT-SoVITS route."""

    def __init__(self) -> None:
        self.base_url = self.base_url + "/tts/gptsovits"
        self.last_error: str | None = None

    @staticmethod
    def _log_request_timing(
        request: GPTSoVITSRequest,
        *,
        elapsed_s: float,
        outcome: str,
        detail: str | None = None,
    ) -> None:
        logger.info(
            "[GPTSoVITSClient] request {} in {:.2f}s text_len={} batch_size={} lang={} detail={}",
            outcome,
            elapsed_s,
            len(request.text),
            request.batch_size,
            request.text_language,
            detail or "-",
        )

    def post(self, request: GPTSoVITSRequest) -> GPTSoVITSResponse | None:  # type: ignore[override]
        if request.ref_audio_path and not Path(request.ref_audio_path).exists():
            self.last_error = f"Reference audio file does not exist: {request.ref_audio_path}"
            logger.error(self.last_error)
            return None

        self.last_error = None
        started = perf_counter()

        try:
            response = self.session.post(self.base_url, json=request.model_dump(exclude_none=True))
            response.raise_for_status()
            response_payload: object = response.json()

            error_message = _extract_error_message(response_payload)
            if error_message is not None:
                self.last_error = error_message
                logger.error("GPTSoVITS server returned error payload: {}", response_payload)
                self._log_request_timing(
                    request,
                    elapsed_s=perf_counter() - started,
                    outcome="failed",
                    detail=error_message,
                )
                return None

            parsed = GPTSoVITSResponseModel.model_validate(response_payload)
            if parsed.audio_type != request.audio_type:
                raise ValueError(f"Expected audio type {request.audio_type}, but got {parsed.audio_type}")

            self._log_request_timing(
                request,
                elapsed_s=perf_counter() - started,
                outcome="succeeded",
                detail=f"audio_rate={parsed.audio_rate}",
            )
            return parsed.to_dict()
        except Exception as exc:
            self.last_error = f"Failed to parse GPTSoVITS response: {exc}"
            logger.error(self.last_error)
            self._log_request_timing(
                request,
                elapsed_s=perf_counter() - started,
                outcome="failed",
                detail=self.last_error,
            )
            return None

    async def asyncpost(self, request: GPTSoVITSRequest) -> GPTSoVITSResponse | None:  # type: ignore[override]
        if request.ref_audio_path and not Path(request.ref_audio_path).exists():
            self.last_error = f"Reference audio file does not exist: {request.ref_audio_path}"
            logger.error(self.last_error)
            return None

        self.async_session = await self.get_async_session()
        self.last_error = None
        started = perf_counter()

        try:
            async with self.async_session.post(self.base_url, json=request.model_dump(exclude_none=True)) as response:
                if response.status != 200:
                    error_body = await response.text()
                    self.last_error = f"GPTSoVITS HTTP {response.status}: {error_body}"
                    logger.error(self.last_error)
                    self._log_request_timing(
                        request,
                        elapsed_s=perf_counter() - started,
                        outcome="failed",
                        detail=self.last_error,
                    )
                    return None

                response_data: object = await response.json()
                error_message = _extract_error_message(response_data)
                if error_message is not None:
                    self.last_error = error_message
                    logger.error("GPTSoVITS server returned error payload: {}", response_data)
                    self._log_request_timing(
                        request,
                        elapsed_s=perf_counter() - started,
                        outcome="failed",
                        detail=error_message,
                    )
                    return None

                try:
                    parsed = GPTSoVITSResponseModel.model_validate(response_data)
                    if parsed.audio_type != request.audio_type:
                        raise ValueError(f"Expected audio type {request.audio_type}, but got {parsed.audio_type}")

                    self._log_request_timing(
                        request,
                        elapsed_s=perf_counter() - started,
                        outcome="succeeded",
                        detail=f"audio_rate={parsed.audio_rate}",
                    )
                    return parsed.to_dict()
                except Exception as exc:
                    self.last_error = f"Failed to parse GPTSoVITS response: {exc}"
                    logger.error("Failed to parse GPTSoVITS response: {}, {}", exc, response_data)
                    self._log_request_timing(
                        request,
                        elapsed_s=perf_counter() - started,
                        outcome="failed",
                        detail=self.last_error,
                    )
                    return None
        finally:
            try:
                await self.async_session.close()
            finally:
                self.async_session = None


def _extract_error_message(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = cast("dict[str, object]", payload)
    code = data.get("code")
    if code in (None, 200, "200"):
        return None
    message = data.get("message", "GPT-SoVITS request failed")
    return str(message)
