from __future__ import annotations

import importlib


def test_asr_request_resolves_path_without_caller_import() -> None:
    asr_client = importlib.import_module("lab.api.clients.asr_client")

    request = asr_client.ASRRequest(file_path="foo.wav")

    assert request.file_path.name == "foo.wav"
