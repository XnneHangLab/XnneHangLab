from __future__ import annotations

import base64
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import Field

from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse
from lab.api.types import GPTSoVITSResponse


class GPTSoVITSRequest(BaseRequest):
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
    def __init__(self):
        self.base_url = self.base_url + "/tts/gptsovits"
        self.last_error: str | None = None

    def post(self, request: GPTSoVITSRequest) -> GPTSoVITSResponse | None:  # type: ignore[override]
        if request.ref_audio_path and not Path(request.ref_audio_path).exists():
            self.last_error = f"Reference audio file does not exist: {request.ref_audio_path}"
            logger.error(self.last_error)
            return None
        self.last_error = None
        response = self.session.post(self.base_url, json=request.model_dump(exclude_none=True))
        response.raise_for_status()
        response = response.json()
        if isinstance(response, dict) and response.get("code") not in (None, 200, "200"):
            self.last_error = str(response.get("message", "GPT-SoVITS request failed"))
            logger.error(f"GPTSoVITS server returned error payload: {response}")
            return None
        try:
            response = GPTSoVITSResponseModel.model_validate(response)
            if response.audio_type != request.audio_type:
                raise ValueError(f"Expected audio type {request.audio_type}, but got {response.audio_type}")
            return response.to_dict()
        except Exception as e:
            self.last_error = f"Failed to parse GPTSoVITS response: {e}"
            logger.error(f"Failed to parse GPTSoVITS response: {e}, {response}")
            return None

    async def asyncpost(self, request: GPTSoVITSRequest) -> GPTSoVITSResponse | None:  # type: ignore[override]
        if request.ref_audio_path and not Path(request.ref_audio_path).exists():
            self.last_error = f"Reference audio file does not exist: {request.ref_audio_path}"
            logger.error(self.last_error)
            return None
        self.async_session = await self.get_async_session()
        self.last_error = None
        try:
            async with self.async_session.post(self.base_url, json=request.model_dump(exclude_none=True)) as response:
                if response.status != 200:
                    error_body = await response.text()
                    self.last_error = f"GPTSoVITS HTTP {response.status}: {error_body}"
                    logger.error(self.last_error)
                    return None
                response_data = await response.json()
                if isinstance(response_data, dict) and response_data.get("code") not in (None, 200, "200"):
                    self.last_error = str(response_data.get("message", "GPT-SoVITS request failed"))
                    logger.error(f"GPTSoVITS server returned error payload: {response_data}")
                    return None
                try:
                    response = GPTSoVITSResponseModel.model_validate(response_data)
                    if response.audio_type != request.audio_type:
                        raise ValueError(f"Expected audio type {request.audio_type}, but got {response.audio_type}")
                    return response.to_dict()
                except Exception as e:
                    self.last_error = f"Failed to parse GPTSoVITS response: {e}"
                    logger.error(f"Failed to parse GPTSoVITS response: {e}, {response_data}")
                    return None
        finally:
            try:
                await self.async_session.close()
            finally:
                self.async_session = None
