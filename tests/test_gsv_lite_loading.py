from __future__ import annotations

# pyright: reportPrivateUsage=false
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

import lab.api.logic.gsv_lite as gsv_lite_module


def _fake_settings(*_args: object, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(
        package=SimpleNamespace(gsv_lite=True),
        agent=SimpleNamespace(tts=SimpleNamespace(gsv_lite=SimpleNamespace(use_bert=False))),
    )


def _spec(character_name: str) -> gsv_lite_module.GSVLiteModelSpec:
    return gsv_lite_module.GSVLiteModelSpec(
        character_name=character_name,
        character_dir=Path(f"./models/gptsovits/{character_name}"),
        gpt_path=Path(f"./models/gptsovits/{character_name}/model.ckpt"),
        sovits_path=Path(f"./models/gptsovits/{character_name}/model.pth"),
        models_dir=Path("./models"),
    )


def test_get_gsv_lite_model_raises_when_not_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_configured_model_spec(*_args: object, **_kwargs: object) -> gsv_lite_module.GSVLiteModelSpec:
        return _spec("baoqiao")

    monkeypatch.setattr(gsv_lite_module, "load_settings_file", _fake_settings)
    monkeypatch.setattr(gsv_lite_module, "_get_configured_model_spec", fake_get_configured_model_spec)
    monkeypatch.setattr(gsv_lite_module, "_gsv_lite_engine", None)
    monkeypatch.setattr(gsv_lite_module, "_loaded_model_spec", None)

    with pytest.raises(HTTPException) as exc_info:
        gsv_lite_module.get_gsv_lite_model()

    assert exc_info.value.status_code == 503
    assert "not initialized" in str(exc_info.value.detail)


def test_get_gsv_lite_model_raises_when_loaded_model_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_configured_model_spec(*_args: object, **_kwargs: object) -> gsv_lite_module.GSVLiteModelSpec:
        return _spec("elaina")

    monkeypatch.setattr(gsv_lite_module, "load_settings_file", _fake_settings)
    monkeypatch.setattr(gsv_lite_module, "_get_configured_model_spec", fake_get_configured_model_spec)
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

    def fake_get_configured_model_spec(*_args: object, **_kwargs: object) -> gsv_lite_module.GSVLiteModelSpec:
        return _spec("luoqixi")

    def fake_resolve_warmup_reference(*_args: object, **_kwargs: object) -> tuple[None, None]:
        return None, None

    monkeypatch.setattr(
        gsv_lite_module,
        "_get_gsv_lite_settings",
        lambda: SimpleNamespace(
            package=SimpleNamespace(gsv_lite=True),
            agent=SimpleNamespace(tts=SimpleNamespace(gsv_lite=SimpleNamespace(use_bert=True))),
            root=SimpleNamespace(root_dir="."),
        ),
    )
    monkeypatch.setattr(gsv_lite_module, "_get_configured_model_spec", fake_get_configured_model_spec)
    monkeypatch.setattr(gsv_lite_module, "_resolve_warmup_reference", fake_resolve_warmup_reference)
    monkeypatch.setattr(gsv_lite_module, "_apply_gsv_lite_monkey_patch", lambda: None)
    monkeypatch.setattr(gsv_lite_module, "_gsv_lite_engine", None)
    monkeypatch.setattr(gsv_lite_module, "_loaded_model_spec", None)

    gsv_tts_module = ModuleType("gsv_tts")
    cast("Any", gsv_tts_module).TTS = FakeTTS
    monkeypatch.setitem(sys.modules, "gsv_tts", gsv_tts_module)

    status = gsv_lite_module.load_gsv_lite_model(force_reload=True)

    assert status["loaded"] is True
    assert captured["gpt_cache"] == [(1, 512), (1, 1024), (1, 2048), (4, 512), (4, 1024)]
    assert captured["use_bert"] is True


def test_get_gsv_lite_use_bert_defaults_to_false_when_missing() -> None:
    settings = SimpleNamespace(agent=SimpleNamespace(tts=SimpleNamespace()))

    assert gsv_lite_module._get_gsv_lite_use_bert(settings) is False


def test_configure_gsv_lite_openjtalk_uses_local_ja_resources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    ja_dir = models_dir / "g2p" / "ja"
    openjtalk_dir = ja_dir / "open_jtalk_dic_utf_8-1.11"
    user_dict_bin = ja_dir / "user.dict"
    openjtalk_dir.mkdir(parents=True)
    user_dict_bin.write_bytes(b"dict")

    calls: list[tuple[str, str | None]] = []

    pyopenjtalk_module = ModuleType("pyopenjtalk")

    def fake_unset_user_dict() -> None:
        calls.append(("unset", None))

    def fake_update_global_jtalk_with_user_dict(path: str) -> None:
        calls.append(("update", path))

    def fake_mecab_dict_index(_src: str, _dst: str) -> None:
        calls.append(("build", None))

    cast("Any", pyopenjtalk_module).unset_user_dict = fake_unset_user_dict
    cast("Any", pyopenjtalk_module).update_global_jtalk_with_user_dict = fake_update_global_jtalk_with_user_dict
    cast("Any", pyopenjtalk_module).mecab_dict_index = fake_mecab_dict_index

    monkeypatch.setitem(sys.modules, "pyopenjtalk", pyopenjtalk_module)
    monkeypatch.delenv("OPEN_JTALK_DICT_DIR", raising=False)

    gsv_lite_module._configure_gsv_lite_openjtalk(models_dir)

    assert os.environ["OPEN_JTALK_DICT_DIR"] == str(openjtalk_dir)
    assert pyopenjtalk_module.OPEN_JTALK_DICT_DIR == str(openjtalk_dir).encode("utf-8")
    assert calls == [("unset", None), ("update", str(user_dict_bin))]
