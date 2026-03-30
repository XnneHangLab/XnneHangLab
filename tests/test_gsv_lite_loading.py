from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pytest
from fastapi import HTTPException

import lab.api.logic.gsv_lite as gsv_lite_module


def _fake_settings(*_args: object, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(package=SimpleNamespace(gsv_lite=True))


def _spec(character_name: str) -> gsv_lite_module.GSVLiteModelSpec:
    return gsv_lite_module.GSVLiteModelSpec(
        character_name=character_name,
        character_dir=Path(f"./models/gptsovits/{character_name}"),
        gpt_path=Path(f"./models/gptsovits/{character_name}/model.ckpt"),
        sovits_path=Path(f"./models/gptsovits/{character_name}/model.pth"),
        models_dir=Path("./models"),
    )


def test_get_gsv_lite_model_raises_when_not_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gsv_lite_module, "load_settings_file", _fake_settings)
    monkeypatch.setattr(gsv_lite_module, "_get_configured_model_spec", lambda *_args, **_kwargs: _spec("baoqiao"))
    monkeypatch.setattr(gsv_lite_module, "_gsv_lite_engine", None)
    monkeypatch.setattr(gsv_lite_module, "_loaded_model_spec", None)

    with pytest.raises(HTTPException) as exc_info:
        gsv_lite_module.get_gsv_lite_model()

    assert exc_info.value.status_code == 503
    assert "not initialized" in str(exc_info.value.detail)


def test_get_gsv_lite_model_raises_when_loaded_model_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gsv_lite_module, "load_settings_file", _fake_settings)
    monkeypatch.setattr(gsv_lite_module, "_get_configured_model_spec", lambda *_args, **_kwargs: _spec("elaina"))
    monkeypatch.setattr(gsv_lite_module, "_gsv_lite_engine", object())
    monkeypatch.setattr(gsv_lite_module, "_loaded_model_spec", _spec("baoqiao"))

    with pytest.raises(HTTPException) as exc_info:
        gsv_lite_module.get_gsv_lite_model()

    assert exc_info.value.status_code == 503
    assert "Currently loaded character: 'baoqiao'" in str(exc_info.value.detail)


def test_load_gsv_lite_model_uses_extended_gpt_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeTTS:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def load_gpt_model(self, *_args: object) -> None:
            return None

        def load_sovits_model(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        gsv_lite_module,
        "_get_gsv_lite_settings",
        lambda: SimpleNamespace(
            package=SimpleNamespace(gsv_lite=True),
            root=SimpleNamespace(root_dir="."),
        ),
    )
    monkeypatch.setattr(gsv_lite_module, "_get_configured_model_spec", lambda *_args, **_kwargs: _spec("luoqixi"))
    monkeypatch.setattr(gsv_lite_module, "_resolve_warmup_reference", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(gsv_lite_module, "_apply_gsv_lite_monkey_patch", lambda: None)
    monkeypatch.setattr(gsv_lite_module, "_gsv_lite_engine", None)
    monkeypatch.setattr(gsv_lite_module, "_loaded_model_spec", None)

    gsv_tts_module = ModuleType("gsv_tts")
    gsv_tts_module.TTS = FakeTTS
    monkeypatch.setitem(sys.modules, "gsv_tts", gsv_tts_module)

    status = gsv_lite_module.load_gsv_lite_model(force_reload=True)

    assert status["loaded"] is True
    assert captured["gpt_cache"] == [(1, 512), (1, 1024), (1, 2048), (4, 512), (4, 1024)]
