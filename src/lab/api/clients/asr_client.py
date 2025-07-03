from __future__ import annotations

# ASRRequest` is not fully defined; you should define `Path`, then call `ASRRequest.model_rebuild()`.
from pathlib import Path  # noqa: TC003

from loguru import logger

from lab._typing import ASRResponse
from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse


class ASRRequest(BaseRequest):
    file_path: Path
    only_text: bool = False


class ASRResponseModel(BaseResponse):
    key: str
    text: str
    timestamp: list[list[int]]

    def to_dict(self) -> ASRResponse:
        return ASRResponse(
            key=self.key,
            text=self.text,
            timestamp=self.timestamp,
        )


# TODO 考虑封装为 ASRClient , VADClient ,然后以一个 interface 定义一个通用的模板。以 post 作为通用的接口。
class ASRClient(BaseClientInterface):
    def __init__(self):
        self.base_url = self.base_url + "/audio/asr"

    def post(self, request: ASRRequest) -> ASRResponse | None:  # type: ignore[override]
        """封装语音识别接口"""
        if not request.file_path.exists():
            logger.error(f"File not found: {request.file_path}")
            return None
        with request.file_path.open("rb") as f:
            response = self.session.post(
                self.base_url, files={"file": f}, params={"only_text": request.only_text}, timeout=10
            )
            response.raise_for_status()
            response = response.json()
            try:
                return ASRResponseModel.model_validate(response).to_dict()  # 转换为 Pydantic 模型
            except Exception as e:
                logger.error(f"Failed to parse ASR response: {e}")
                return None

    async def asyncpost(self, request: ASRRequest) -> ASRResponse | None:  # type: ignore[override]
        """封装语音识别接口的异步版本"""
        self.async_session = await self.get_async_session()
        if not request.file_path.exists():
            logger.error(f"File not found: {request.file_path}")
            return None
        with request.file_path.open("rb") as f:
            async with self.async_session.post(
                self.base_url, data={"file": f}, params={"only_text": request.only_text}
            ) as response:
                if response.status != 200:
                    logger.error(f"Failed to get a valid response: {response.status}")
                    return None
                response_data = await response.json()
                try:
                    return ASRResponseModel.model_validate(response_data).to_dict()  # 转换为 Pydantic 模型
                except Exception as e:
                    logger.error(f"Failed to parse ASR response: {e}")
                    return None
                finally:
                    await self.async_session.close()
