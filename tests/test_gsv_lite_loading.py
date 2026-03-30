from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
    assert "not loaded" in str(exc_info.value.detail)


def test_get_gsv_lite_model_raises_when_loaded_model_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gsv_lite_module, "load_settings_file", _fake_settings)
    monkeypatch.setattr(gsv_lite_module, "_get_configured_model_spec", lambda *_args, **_kwargs: _spec("elaina"))
    monkeypatch.setattr(gsv_lite_module, "_gsv_lite_engine", object())
    monkeypatch.setattr(gsv_lite_module, "_loaded_model_spec", _spec("baoqiao"))

    with pytest.raises(HTTPException) as exc_info:
        gsv_lite_module.get_gsv_lite_model()

    assert exc_info.value.status_code == 503
    assert "Currently loaded character: 'baoqiao'" in str(exc_info.value.detail)
