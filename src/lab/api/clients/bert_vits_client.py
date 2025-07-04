from __future__ import annotations

import base64
from typing import Literal

from loguru import logger

from lab._typing import BERTVITSResponse
from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse


class BERTVITSRequest(BaseRequest):
    audio_type: Literal["opus"]
    text: str


class BERTVITSResponseModel(BaseResponse):
    audio_type: Literal["opus"]
    audio_rate: int
    audio_byte: str  # base64.b64encode(opus_bytes).decode("utf-8")

    def to_dict(self) -> BERTVITSResponse:
        return BERTVITSResponse(
            audio_type=self.audio_type,
            audio_rate=self.audio_rate,
            audio_byte=base64.b64decode(self.audio_byte),
        )


class BERVITSClient(BaseClientInterface):
    def __init__(self):
        self.base_url = self.base_url + "/tts/bert_vits"

    def post(self, request: BERTVITSRequest) -> BERTVITSResponse | None:  # type: ignore[override]
        response = self.session.post(self.base_url, json=request.model_dump())
        response.raise_for_status()
        response = response.json()
        try:
            response = BERTVITSResponseModel.model_validate(response)  # 转换为 Pydantic 模型
            if response.audio_type != request.audio_type:
                raise ValueError(f"Expected audio type {request.audio_type}, but got {response.audio_type}")
            return response.to_dict()
        except Exception as e:
            logger.error(f"Failed to parse BERT_VITS response: {e}, {response}")
            return None

    async def asyncpost(self, request: BERTVITSRequest) -> BERTVITSResponse | None:  # type: ignore[override]
        """
        Asynchronous wrapper for the post method.
        """
        # bert-vits 的请求通常很久。所以生产环境应该异步。
        self.async_session = await self.get_async_session()
        async with self.async_session.post(self.base_url, json=request.model_dump()) as response:
            if response.status != 200:
                logger.error(f"Failed to get a valid response: {response.status}")
                return None
            response_data = await response.json()
            try:
                response = BERTVITSResponseModel.model_validate(response_data)  # 转换为 Pydantic 模型
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
