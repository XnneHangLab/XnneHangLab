from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

import lab.api.logic.genie_tts as genie

if TYPE_CHECKING:
    from pathlib import Path


def test_genie_prewarms_all_embeddings_and_checks_capacity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache: dict[str, Any] = {}
    updates: list[str] = []
    prompt_cache = SimpleNamespace(capacity=2)

    class Reference:
        _prompt_cache = prompt_cache

        def __new__(cls, path: str, *_args: Any, **_kwargs: Any):
            if path not in cache:
                obj = super().__new__(cls)
                obj.path = path
                obj.global_emb = None
                obj.global_emb_advanced = None
                cache[path] = obj
            return cache[path]

        def update_global_emb(self, encoder: object) -> None:
            assert encoder is not None
            if self.global_emb is None:
                updates.append(self.path)
                self.global_emb = self.global_emb_advanced = "embedding"

    refs = [(tmp_path / "1.wav", "one", None), (tmp_path / "2.wav", "two", None)]
    monkeypatch.setattr(genie, "resolve_all_voice_assets", lambda *_args: refs)
    monkeypatch.setattr(
        genie,
        "_resolve_active_profile",
        lambda *_args: SimpleNamespace(character=SimpleNamespace(tts=SimpleNamespace(voice="test"))),
    )
    monkeypatch.setitem(sys.modules, "genie_tts.Audio.ReferenceAudio", SimpleNamespace(ReferenceAudio=Reference))
    monkeypatch.setitem(
        sys.modules,
        "genie_tts.ModelManager",
        SimpleNamespace(model_manager=SimpleNamespace(get=lambda _: SimpleNamespace(PROMPT_ENCODER=object()))),
    )
    spec = genie.GenieTTSModelSpec("test", tmp_path, tmp_path, "Chinese", False)
    settings = cast("Any", None)  # Resolvers are replaced above; no settings file is read.
    genie._warmup_genie_voice_references(settings, spec)
    genie._warmup_genie_voice_references(settings, spec)
    assert len(cache) == 2 and len(updates) == 2
    refs.append((tmp_path / "3.wav", "three", None))
    with pytest.raises(ValueError, match="cache capacity"):
        genie._warmup_genie_voice_references(settings, spec)
    assert len(cache) == 2
    refs[:] = [(tmp_path / "1.wav", "", None)]
    with pytest.raises(ValueError, match="missing ref_text"):
        genie._warmup_genie_voice_references(settings, spec)
    refs[:] = [(tmp_path / "1.wav", "one", None), (tmp_path / "1.wav", "conflict", None)]
    with pytest.raises(ValueError, match="conflicting ref_text"):
        genie._warmup_genie_voice_references(settings, spec)


def test_loading_character_clears_reference_cache_only_when_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    module = SimpleNamespace(
        load_character=lambda **_kwargs: events.append("load"),
        clear_reference_audio_cache=lambda: events.append("clear"),
    )
    spec = genie.GenieTTSModelSpec("test", tmp_path, tmp_path, "Chinese", False)
    settings = SimpleNamespace(agent=SimpleNamespace(tts=SimpleNamespace(provider="genie_tts")))
    monkeypatch.setattr(genie, "_get_genie_tts_settings", lambda: settings)
    monkeypatch.setattr(genie, "_get_configured_model_spec", lambda *_args: spec)
    monkeypatch.setattr(genie, "_configure_genie_tts_environment", lambda *_args: None)
    monkeypatch.setattr(genie, "_import_genie_tts_module", lambda *_args: module)
    monkeypatch.setattr(genie, "get_genie_tts_status", lambda: {"loaded": True})
    monkeypatch.setattr(genie, "_release_engine", lambda: events.append("release"))
    monkeypatch.setattr(genie, "_genie_tts_module", None)
    monkeypatch.setattr(genie, "_loaded_model_spec", None)
    genie.load_genie_tts_model()
    genie.load_genie_tts_model()
    assert events == ["load", "clear"]
    genie.reload_genie_tts_model()
    assert events == ["load", "clear", "release", "load", "clear"]
