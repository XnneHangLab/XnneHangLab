# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingTypeArgument=false

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp

from lab.api.clients.base_client_interface import BaseClientInterface, BaseRequest, BaseResponse
from lab.asr.converter import convert_asr_response_to_sentences
from lab.asr.types import ASRResponse, Sentence
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.logger.logger_group import logger  # pyright: ignore[reportAttributeAccessIssue]

if TYPE_CHECKING:
    from pathlib import Path

_asr_logger = logger.bind(group="asr")


class ASRRequest(BaseRequest):
    file_path: Path
    only_text: bool = False
    model_name: str | None = None


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
        self.base_url = self.base_url
        self.last_error: str | None = None

    def _resolve_qwen_route_model(self, request: ASRRequest) -> str:
        """解析 Qwen3-ASR 调用使用的端点模型名。

        Args:
            request: 当前请求对象。

        Returns:
            str: 路由使用的模型名。

        Raises:
            RuntimeError: Qwen3-ASR 服务未启用时抛出。
        """
        settings = load_settings_file("lab.toml", XnneHangLabSettings)
        if not settings.package.qwen_asr:
            raise RuntimeError("Qwen3-ASR is disabled in lab.toml")

        if request.model_name:
            return request.model_name

        preload_models = settings.asr.qwen_asr.preload_models
        if preload_models:
            return preload_models[0]
        return "0.6B"

    def _resolve_base_url(self, request: ASRRequest) -> str:
        """根据当前配置解析 ASR 请求地址。

        Args:
            request: 当前请求对象。

        Returns:
            str: 目标接口地址。

        Raises:
            RuntimeError: 目标服务未启用时抛出。
        """
        settings = load_settings_file("lab.toml", XnneHangLabSettings)
        if settings.asr.asr_model_provider == "qwen":
            model_name = self._resolve_qwen_route_model(request)
            return f"{self.base_url}/asr/qwen-asr/{model_name}/transcribe"

        if not settings.package.asr:
            raise RuntimeError("Sherpa-ONNX is disabled in lab.toml")
        return f"{self.base_url}/asr/funasr/transcribe"

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
            self.last_error = f"File not found: {request.file_path}"
            _asr_logger.error(self.last_error)
            return None

        self.last_error = None

        try:
            base_url = self._resolve_base_url(request)
            with request.file_path.open("rb") as file:
                response = self.session.post(base_url, files={"file": file})
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
        """异步调用 ASR 接口。

        Args:
            request: 包含待识别音频路径的请求对象。

        Returns:
            ASRResponse | None: 成功时返回标准 ASR 响应，失败时返回 None。

        Raises:
            None.
        """
        self.async_session = await self.get_async_session()
        if self.async_session is None:
            self.last_error = "Failed to create async ASR session."
            _asr_logger.error(self.last_error)
            return None
        if not request.file_path.exists():
            self.last_error = f"File not found: {request.file_path}"
            _asr_logger.error(self.last_error)
            return None

        try:
            base_url = self._resolve_base_url(request)
            with request.file_path.open("rb") as file:
                form = aiohttp.FormData()
                form.add_field("file", file, filename=request.file_path.name)
                async with self.async_session.post(base_url, data=form) as response:
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
            if self.async_session is not None:
                await self.async_session.close()

        try:
            return ASRResponseModel.model_validate(payload).to_dict()
        except Exception as exc:
            self.last_error = f"Failed to parse ASR response: {exc}"
            _asr_logger.error(f"Failed to parse ASR response: {exc}, {payload}")
            return None
