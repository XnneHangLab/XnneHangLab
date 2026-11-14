from __future__ import annotations

import io
import sys
from collections import OrderedDict
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import lab.api.logic.faster_qwen_tts as qwen
from lab.api.routes import faster_qwen_tts as qwen_routes

if TYPE_CHECKING:
    from pathlib import Path


class FakeQwen:
    def __init__(self) -> None:
        self.model = self
        self.extractions: list[dict[str, Any]] = []
        self.generated: list[Any] = []

    def _load_ref_audio_with_silence(self, path: Path) -> bytes:
        return path.read_bytes()

    def create_voice_clone_prompt(self, **kwargs: Any) -> list[object]:
        self.extractions.append(kwargs)
        audio = kwargs["ref_audio"]
        return [object() for _ in audio] if isinstance(audio, list) else [object()]

    def generate_voice_clone(self, **kwargs: Any) -> tuple[list[np.ndarray], int]:
        assert "ref_audio" not in kwargs
        self.generated.append(kwargs["voice_clone_prompt"])
        return [np.zeros(24, dtype=np.float32)], 24000

    def generate_voice_clone_streaming(self, **kwargs: Any):
        self.generate_voice_clone(**kwargs)
        yield [np.zeros(24, dtype=np.float32)], 24000, {}


@pytest.fixture
def qwen_model(monkeypatch: pytest.MonkeyPatch) -> FakeQwen:
    model = FakeQwen()
    monkeypatch.setattr(qwen, "_voice_prompt_cache", OrderedDict())
    monkeypatch.setattr(qwen, "get_qwen_tts_model", lambda: model)
    return model


def test_qwen_uploads_and_stream_share_content_cache(qwen_model: FakeQwen, tmp_path: Path) -> None:
    local = tmp_path / "ref.wav"
    local.write_bytes(b"same audio")
    # Startup's local reference must match uploads with arbitrary temporary paths.
    with qwen._model_lock:
        prompt = qwen._get_voice_clone_prompt(qwen_model, local, "reference")
    app = FastAPI()
    app.include_router(qwen_routes.router)
    with TestClient(app) as client:
        for endpoint in ["/generate", "/generate", "/generate/stream"]:
            response = client.post(
                f"/tts/qwen-tts{endpoint}",
                data={"text": "hello", "ref_text": "reference"},
                files={"ref_audio": ("ref.wav", io.BytesIO(b"same audio"), "audio/wav")},
            )
            assert response.status_code == 200
            if endpoint.endswith("stream"):
                assert '"type": "error"' not in response.text
            else:
                assert response.content[:4] == b"RIFF"
    assert len(qwen_model.extractions) == 1
    assert all(item is prompt for item in qwen_model.generated)
    assert len(qwen._voice_prompt_cache) == 1


def test_qwen_content_text_changes_lru_and_failed_extraction(
    qwen_model: FakeQwen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(qwen, "_MAX_CACHED_VOICE_PROMPTS", 2)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"first")
    first = qwen._get_voice_clone_prompt(qwen_model, ref, "a")
    qwen._get_voice_clone_prompt(qwen_model, ref, "b")
    assert qwen._get_voice_clone_prompt(qwen_model, ref, "a") is first
    ref.write_bytes(b"changed")
    qwen._get_voice_clone_prompt(qwen_model, ref, "a")
    assert len(qwen._voice_prompt_cache) == 2
    ref.write_bytes(b"first")
    qwen._get_voice_clone_prompt(qwen_model, ref, "b")  # Evicted rather than the recently used 'a'.
    assert len(qwen_model.extractions) == 4
    before = dict(qwen._voice_prompt_cache)

    def fail(**_kwargs: Any) -> Any:
        raise RuntimeError("extraction failed")

    monkeypatch.setattr(qwen_model, "create_voice_clone_prompt", fail)
    with pytest.raises(RuntimeError, match="extraction failed"):
        qwen._get_voice_clone_prompt(qwen_model, ref, "new text")
    assert dict(qwen._voice_prompt_cache) == before


def test_qwen_load_prewarms_all_references_and_reload_clears_cache(
    qwen_model: FakeQwen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab.config_manager import XnneHangLabSettings

    settings = XnneHangLabSettings()
    settings.root.root_dir = str(tmp_path)
    settings.agent.tts.provider = "qwen_tts"
    settings.agent.memory_agent_profile = "profile.toml"
    settings.agent.qwen_tts.device = "cpu"
    refs = []
    for i in range(3):
        audio = tmp_path / f"{i}.wav"
        audio.write_bytes(str(i).encode())
        refs.append((audio, f"text{i}", None))
    refs.append(refs[0])  # Shared reference assets are encoded only once in the batch.
    monkeypatch.setattr(qwen, "_get_qwen_tts_settings", lambda: settings)
    monkeypatch.setattr(qwen, "_resolve_model_source", lambda *_args: "fake-model")
    monkeypatch.setattr(qwen, "_qwen_tts_engine", None)
    monkeypatch.setattr(qwen, "resolve_all_voice_assets", lambda *_args: refs)
    monkeypatch.setattr(qwen, "resolve_voice_assets", lambda *_args: refs[0])
    monkeypatch.setattr(
        qwen.Profile,
        "from_toml",
        lambda *_args: SimpleNamespace(character=SimpleNamespace(tts=SimpleNamespace(voice="test"))),
    )
    monkeypatch.setitem(
        sys.modules,
        "faster_qwen3_tts",
        SimpleNamespace(FasterQwen3TTS=SimpleNamespace(from_pretrained=lambda *_a, **_kw: qwen_model)),
    )
    monkeypatch.setattr(qwen, "_loaded_model_name", None)
    monkeypatch.setattr(qwen, "_loaded_model_source", None)
    # Avoid GPU initialization in this model-free test.
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    assert qwen.load_qwen_tts_model()["loaded"] is True
    assert len(qwen_model.extractions) == 1
    assert qwen_model.extractions[0]["ref_text"] == ["text0", "text1", "text2"]
    assert len(qwen_model.generated) == 1
    assert qwen_model.generated[0] is qwen._get_voice_clone_prompt(qwen_model, refs[0][0], "text0")
    assert len(qwen._voice_prompt_cache) == 3
    qwen.load_qwen_tts_model()
    assert len(qwen_model.extractions) == 1
    assert len(qwen_model.generated) == 1
    qwen.reload_qwen_tts_model()
    assert len(qwen_model.extractions) == 2
    assert len(qwen_model.generated) == 2
    monkeypatch.setattr(qwen, "_MAX_CACHED_VOICE_PROMPTS", 2)
    with pytest.raises(ValueError, match="cache capacity"):
        qwen.reload_qwen_tts_model()
    assert qwen._qwen_tts_engine is None
    assert not qwen._voice_prompt_cache

    monkeypatch.setattr(qwen, "_MAX_CACHED_VOICE_PROMPTS", 10)
    original_generate = qwen_model.generate_voice_clone
    monkeypatch.setattr(qwen_model, "generate_voice_clone", lambda **_kwargs: ([], 24000))
    with pytest.raises(RuntimeError, match="returned no audio"):
        qwen.load_qwen_tts_model()
    assert qwen._qwen_tts_engine is None
    assert not qwen._voice_prompt_cache

    monkeypatch.setattr(qwen_model, "generate_voice_clone", original_generate)
    monkeypatch.setattr(qwen_model, "create_voice_clone_prompt", lambda **_kwargs: [])
    with pytest.raises(RuntimeError, match="prompt count"):
        qwen.load_qwen_tts_model()
    assert qwen._qwen_tts_engine is None
    assert not qwen._voice_prompt_cache

    refs[0] = (refs[0][0], "", None)
    with pytest.raises(qwen.HTTPException) as exc_info:
        qwen.load_qwen_tts_model()
    assert exc_info.value.status_code == 400
    assert qwen._qwen_tts_engine is None
    assert not qwen._voice_prompt_cache
