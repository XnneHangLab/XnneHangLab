from __future__ import annotations

from pathlib import Path

import requests
from loguru import logger
from pydantic import BaseModel

from lab._typing import ASRResponse, VadResponse


class ASRRequest(BaseModel):
    file_path: Path
    only_text: bool = False


class VADRequest(BaseModel):
    file_path: Path


class ASRResponseModel(BaseModel):
    key: str
    text: str
    timestamp: list[list[int]]

    def to_dict(self) -> ASRResponse:
        return ASRResponse(
            key=self.key,
            text=self.text,
            timestamp=self.timestamp,
        )

    class Config:
        extra = "ignore"  # 忽略额外字段


class VADResponseModel(BaseModel):
    key: str
    timestamp: list[list[int]]
    audio_length: int

    def to_dict(self) -> VadResponse:
        return VadResponse(
            key=self.key,
            timestamp=self.timestamp,
            audio_length=self.audio_length,
        )

    class Config:
        extra = "ignore"  # 忽略额外字段


class AudioAPIClient:
    def __init__(self, base_url: str = "http://localhost:12393"):
        self.base_url = f"{base_url}/audio"
        self.asr_url = f"{self.base_url}/asr"
        self.vad_url = f"{self.base_url}/vad"
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def recognize_audio(self, request: ASRRequest) -> ASRResponse | None:
        """封装语音识别接口"""
        if not request.file_path.exists():
            logger.error(f"File not found: {request.file_path}")
            return None
        with request.file_path.open("rb") as f:
            response = self.session.post(
                self.asr_url, files={"file": f}, params={"only_text": request.only_text}, timeout=10
            )
            response.raise_for_status()
            response = response.json()
            try:
                return ASRResponseModel.model_validate(response).to_dict()  # 转换为 Pydantic 模型
            except Exception as e:
                logger.error(f"Failed to parse ASR response: {e}")
                return None

    def vad_audio(self, request: VADRequest) -> VadResponse | None:
        """封装语音活动检测接口"""
        if not request.file_path.exists():
            logger.error(f"File not found: {request.file_path}")
            return None
        with request.file_path.open("rb") as f:
            response = self.session.post(self.vad_url, files={"file": f}, timeout=10)
            response.raise_for_status()
            response = response.json()
            try:
                return VADResponseModel.model_validate(response).to_dict()  # 转换为 Pydantic 模型
            except Exception as e:
                logger.error(f"Failed to parse VAD response: {e}")
                return None


# # Streamlit 使用示例
# client = AudioAPIClient()
# result = client.recognize_audio(ASRRequest(file_path="test.wav"))
