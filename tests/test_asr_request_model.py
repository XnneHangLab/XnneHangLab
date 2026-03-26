from __future__ import annotations

import importlib


def test_asr_request_instantiates_without_runtime_path_in_caller_namespace() -> None:
    """只验证请求模型可实例化，不触发任何 ASR 推理或模型加载。"""
    asr_client = importlib.import_module("lab.api.clients.asr_client")

    request = asr_client.ASRRequest(file_path="foo.wav")

    assert request.file_path.name == "foo.wav"
