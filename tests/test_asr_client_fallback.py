from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from lab.api.clients.asr_client import ASRClient, ASRRequest
from lab.conversations.conversation_utils import process_user_input


class InspectableASRClient(ASRClient):
    def resolve_base_url(self, request: ASRRequest) -> str:
        return self._resolve_base_url(request)


def _make_settings(*, provider: str, sherpa_asr: bool, qwen_asr: bool) -> SimpleNamespace:
    return SimpleNamespace(
        asr=SimpleNamespace(
            asr_model_provider=provider,
            qwen_asr=SimpleNamespace(preload_models=[]),
        ),
        package=SimpleNamespace(
            sherpa_asr=sherpa_asr,
            qwen_asr=qwen_asr,
        ),
    )


def test_asr_client_falls_back_to_enabled_sherpa(monkeypatch: pytest.MonkeyPatch) -> None:
    from lab.api.clients import asr_client as asr_client_module

    def fake_load_settings_file(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return _make_settings(provider="qwen", sherpa_asr=True, qwen_asr=False)

    monkeypatch.setattr(
        asr_client_module,
        "load_settings_file",
        fake_load_settings_file,
    )

    client = InspectableASRClient()
    base_url = client.resolve_base_url(ASRRequest(file_path=Path("dummy.wav")))

    assert base_url.endswith("/asr/sherpa/transcribe")


def test_asr_client_raises_clear_error_when_all_asr_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from lab.api.clients import asr_client as asr_client_module

    def fake_load_settings_file(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return _make_settings(provider="sherpa", sherpa_asr=False, qwen_asr=False)

    monkeypatch.setattr(
        asr_client_module,
        "load_settings_file",
        fake_load_settings_file,
    )

    client = InspectableASRClient()

    with pytest.raises(RuntimeError, match="use text input"):
        client.resolve_base_url(ASRRequest(file_path=Path("dummy.wav")))


@pytest.mark.anyio
async def test_process_user_input_surfaces_asr_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from lab.conversations import conversation_utils as conversation_utils_module

    monkeypatch.chdir(tmp_path)

    class FakeASRClient:
        def __init__(self) -> None:
            self.last_error = "ASR is disabled in lab.toml. Enable [package].sherpa_asr or [package].qwen_asr, or use text input."

        async def asyncpost(self, _request: object) -> None:
            return None

    monkeypatch.setattr(conversation_utils_module, "ASRClient", FakeASRClient)

    async def fake_websocket_send(_payload: str) -> None:
        return None

    audio = np.zeros(1600, dtype=np.float32)

    with pytest.raises(RuntimeError, match="use text input"):
        await process_user_input(audio, fake_websocket_send)
