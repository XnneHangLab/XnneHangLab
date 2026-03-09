from __future__ import annotations

import base64
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import Field

from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse
from lab.api.types import GPTSoVITSResponse


class GPTSoVITSRequest(BaseRequest):
    text: str  # 必须传入
    ref_audio_path: str  # 不传入 ref 约束的 gptsovits 在 fast_gsv 推理中简直一团糟，所以我们必须约束他
    # character: str = Field(default="elaina") # 暂时不支持多角色
    audio_type: Literal["mp3"] = Field(default="mp3")
    text_language: str = Field(default="ja")  # 默认日语
    speed: float = Field(default=1.0)  # 语速
    temperature: float = Field(default=1.0)  # 温度


class GPTSoVITSResponseModel(BaseResponse):
    audio_type: Literal["mp3"]
    audio_rate: int
    audio_byte: str  # base64.b64encode(opus_bytes).decode("utf-8")

    def to_dict(self) -> GPTSoVITSResponse:
        return GPTSoVITSResponse(
            audio_type=self.audio_type,
            audio_rate=self.audio_rate,
            audio_byte=base64.b64decode(self.audio_byte),
        )


class GPTSoVITSClient(BaseClientInterface):
    def __init__(self):
        self.base_url = self.base_url + "/tts/gptsovits"

    def post(self, request: GPTSoVITSRequest) -> GPTSoVITSResponse | None:  # type: ignore[override]
        if not Path(request.ref_audio_path).exists():
            logger.error(f"Reference audio file does not exist: {request.ref_audio_path}")
            return None
        response = self.session.post(self.base_url, json=request.model_dump())
        response.raise_for_status()
        response = response.json()
        try:
            response = GPTSoVITSResponseModel.model_validate(response)  # 转换为 Pydantic 模型
            if response.audio_type != request.audio_type:
                raise ValueError(f"Expected audio type {request.audio_type}, but got {response.audio_type}")
            return response.to_dict()
        except Exception as e:
            logger.error(f"Failed to parse GPTSoVITS response: {e}, {response}")
            return None

    async def asyncpost(self, request: GPTSoVITSRequest) -> GPTSoVITSResponse | None:  # type: ignore[override]
        """
        Asynchronous wrapper for the post method.
        """
        # bert-vits 的请求通常很久。所以生产环境应该异步。
        if not Path(request.ref_audio_path).exists():
            logger.error(f"Reference audio file does not exist: {request.ref_audio_path}")
            return None
        self.async_session = await self.get_async_session()
        async with self.async_session.post(self.base_url, json=request.model_dump()) as response:
            if response.status != 200:
                logger.error(f"Failed to get a valid response: {response.status}")
                return None
            response_data = await response.json()
            try:
                response = GPTSoVITSResponseModel.model_validate(response_data)  # 转换为 Pydantic 模型
                if response.audio_type != request.audio_type:
                    raise ValueError(f"Expected audio type {request.audio_type}, but got {response.audio_type}")
                return response.to_dict()
            except Exception as e:
                logger.error(f"Failed to parse BERT_VITS response: {e}, {response}")
                return None
            finally:
                await self.async_session.close()


# bert_vits_client = BERVITSClient()
# result = await bert_vits_client.asyncpost(BERTVITSRequest(text="你好，世界！", audio_type="opus"))
