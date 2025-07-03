from __future__ import annotations

# ASRRequest` is not fully defined; you should define `Path`, then call `ASRRequest.model_rebuild()`.
from pathlib import Path  # noqa: TC003

from loguru import logger

from lab._typing import VadResponse
from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse


class VADRequest(BaseRequest):
    file_path: Path


class VADResponseModel(BaseResponse):
    key: str
    timestamp: list[list[int]]
    audio_length: int

    def to_dict(self) -> VadResponse:
        return VadResponse(
            key=self.key,
            timestamp=self.timestamp,
            audio_length=self.audio_length,
        )


class VADClient(BaseClientInterface):
    def __init__(self):
        self.base_url = self.base_url + "/audio/vad"

    def post(self, request: VADRequest) -> VadResponse | None:  # type: ignore[override]
        """封装语音活动检测接口"""
        if not request.file_path.exists():
            logger.error(f"File not found: {request.file_path}")
            return None
        with request.file_path.open("rb") as f:
            response = self.session.post(self.base_url, files={"file": f}, timeout=10)
            response.raise_for_status()
            response = response.json()
            try:
                return VADResponseModel.model_validate(response).to_dict()  # 转换为 Pydantic 模型
            except Exception as e:
                logger.error(f"Failed to parse VAD response: {e}")
                return None
