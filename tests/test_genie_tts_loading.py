# pyright: reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownMemberType=false

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import lab.api.logic.genie_tts as genie_tts_module


def _fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        package=SimpleNamespace(genie_tts=True),
        agent=SimpleNamespace(
            speaker_lang="ZH",
            tts=SimpleNamespace(genie_tts=SimpleNamespace(use_roberta=False, language="")),
        ),
        root=SimpleNamespace(root_dir="."),
    )


def _spec(character_name: str) -> genie_tts_module.GenieTTSModelSpec:
    return genie_tts_module.GenieTTSModelSpec(
        character_name=character_name,
        character_dir=Path(f"./models/genie-tts/{character_name}"),
        onnx_model_dir=Path(f"./models/genie-tts/{character_name}/tts_models"),
        language="Chinese",
        use_roberta=False,
    )


def test_get_genie_tts_model_raises_when_not_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(genie_tts_module, "load_settings_file", lambda *_args, **_kwargs: _fake_settings())
    monkeypatch.setattr(genie_tts_module, "_get_configured_model_spec", lambda *_args, **_kwargs: _spec("baoqiao"))
    monkeypatch.setattr(genie_tts_module, "_genie_tts_module", None)
    monkeypatch.setattr(genie_tts_module, "_loaded_model_spec", None)

    with pytest.raises(HTTPException) as exc_info:
        genie_tts_module.get_genie_tts_model()

    assert exc_info.value.status_code == 503
    assert "not initialized" in str(exc_info.value.detail)


def test_get_genie_tts_model_raises_when_loaded_model_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(genie_tts_module, "load_settings_file", lambda *_args, **_kwargs: _fake_settings())
    monkeypatch.setattr(genie_tts_module, "_get_configured_model_spec", lambda *_args, **_kwargs: _spec("elaina"))
    monkeypatch.setattr(genie_tts_module, "_genie_tts_module", object())
    monkeypatch.setattr(genie_tts_module, "_loaded_model_spec", _spec("baoqiao"))

    with pytest.raises(HTTPException) as exc_info:
        genie_tts_module.get_genie_tts_model()

    assert exc_info.value.status_code == 503
    assert "Currently loaded character: 'baoqiao'" in str(exc_info.value.detail)


def test_resolve_model_dir_prefers_infer_config_key(tmp_path: Path) -> None:
    character_dir = tmp_path / "models" / "gptsovits" / "baoqiao"
    model_dir = character_dir / "custom_genie"
    model_dir.mkdir(parents=True)

    resolved = genie_tts_module._resolve_model_dir_from_infer_config(
        character_dir,
        {"genie_model_dir": "custom_genie"},
    )

    assert resolved == model_dir.resolve()


def test_resolve_default_model_dir_accepts_character_root_when_onnx_files_are_in_root(tmp_path: Path) -> None:
    character_dir = tmp_path / "models" / "genie-tts" / "baoqiao"
    character_dir.mkdir(parents=True)
    (character_dir / "vits_fp32.onnx").write_bytes(b"onnx")
    (character_dir / "t2s_encoder_fp32.onnx").write_bytes(b"onnx")

    resolved = genie_tts_module._resolve_default_model_dir(character_dir)

    assert resolved == character_dir.resolve()


def test_get_genie_tts_use_roberta_defaults_to_false_when_missing() -> None:
    settings = SimpleNamespace(agent=SimpleNamespace(tts=SimpleNamespace()))

    assert genie_tts_module._get_genie_tts_use_roberta(settings) is False


def test_resolve_language_prefers_lab_toml_override() -> None:
    settings = SimpleNamespace(
        agent=SimpleNamespace(
            speaker_lang="ZH",
            tts=SimpleNamespace(genie_tts=SimpleNamespace(language="Japanese")),
        )
    )

    resolved = genie_tts_module._resolve_language({"language": "English"}, settings)

    assert resolved == "Japanese"


def test_resolve_language_falls_back_to_auto_without_lab_toml_or_infer_json() -> None:
    settings = SimpleNamespace(
        agent=SimpleNamespace(
            speaker_lang="ZH",
            tts=SimpleNamespace(genie_tts=SimpleNamespace(language="")),
        )
    )

    resolved = genie_tts_module._resolve_language({}, settings)

    assert resolved == "auto"


def test_resolve_warmup_ref_audio_and_text_prefers_default_emotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(root=SimpleNamespace(root_dir=str(tmp_path)))
    ref_audio = tmp_path / "models" / "genie-tts" / "baoqiao" / "ref_audios" / "default.wav"
    ref_audio.parent.mkdir(parents=True)
    ref_audio.write_bytes(b"wav")

    profile = SimpleNamespace(
        character=SimpleNamespace(
            tts=SimpleNamespace(
                emotions={
                    "default": SimpleNamespace(path="ref_audios/default.wav", ref_text="default ref"),
                    "happy": SimpleNamespace(path="ref_audios/happy.wav", ref_text="happy ref"),
                }
            )
        )
    )
    monkeypatch.setattr(genie_tts_module, "_resolve_active_profile", lambda *_args, **_kwargs: profile)

    resolved_audio, resolved_text = genie_tts_module._resolve_warmup_ref_audio_and_text(settings, "baoqiao")

    assert resolved_audio == ref_audio.resolve()
    assert resolved_text == "default ref"


def test_warmup_genie_tts_model_uses_ref_text_for_warmup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = SimpleNamespace(
        package=SimpleNamespace(genie_tts=True),
        agent=SimpleNamespace(
            speaker_lang="ZH",
            tts=SimpleNamespace(genie_tts=SimpleNamespace(use_roberta=False, language="auto")),
        ),
        root=SimpleNamespace(root_dir=str(tmp_path)),
    )
    spec = genie_tts_module.GenieTTSModelSpec(
        character_name="baoqiao",
        character_dir=tmp_path / "models" / "genie-tts" / "baoqiao",
        onnx_model_dir=tmp_path / "models" / "genie-tts" / "baoqiao",
        language="auto",
        use_roberta=False,
    )
    ref_audio = tmp_path / "models" / "genie-tts" / "baoqiao" / "ref_audios" / "default.wav"
    ref_audio.parent.mkdir(parents=True)
    ref_audio.write_bytes(b"wav")

    captured: dict[str, object] = {}

    async def _fake_synthesize_once(*, text: str, ref_audio: Path | None, ref_text: str | None) -> bytes:
        captured["text"] = text
        captured["ref_audio"] = ref_audio
        captured["ref_text"] = ref_text
        return b"RIFFfake"

    monkeypatch.setattr(genie_tts_module, "_get_genie_tts_settings", lambda: settings)
    monkeypatch.setattr(genie_tts_module, "_get_configured_model_spec", lambda *_args, **_kwargs: spec)
    monkeypatch.setattr(
        genie_tts_module,
        "_resolve_warmup_ref_audio_and_text",
        lambda *_args, **_kwargs: (ref_audio.resolve(), "default ref"),
    )
    monkeypatch.setattr(genie_tts_module, "synthesize_once", _fake_synthesize_once)
    monkeypatch.setattr(genie_tts_module, "read_wav_sample_rate", lambda _wav_bytes: 32000)
    monkeypatch.setattr(genie_tts_module, "get_genie_tts_status", lambda: {"loaded": True})

    status = asyncio.run(genie_tts_module.warmup_genie_tts_model())

    assert status == {"loaded": True}
    assert captured["text"] == "default ref"
    assert captured["ref_audio"] == ref_audio.resolve()
    assert captured["ref_text"] == "default ref"


def test_resolve_genie_tts_submodule_src_dir(tmp_path: Path) -> None:
    settings = SimpleNamespace(root=SimpleNamespace(root_dir=str(tmp_path)))

    resolved = genie_tts_module._resolve_genie_tts_submodule_src_dir(settings)

    assert resolved == (tmp_path / "packages" / "Genie-TTS" / "src").resolve()


def test_resolve_character_dir_prefers_genie_tts_root(tmp_path: Path) -> None:
    settings = SimpleNamespace(root=SimpleNamespace(root_dir=str(tmp_path)))
    preferred = tmp_path / "models" / "genie-tts" / "baoqiao"
    legacy = tmp_path / "models" / "gptsovits" / "baoqiao"
    preferred.mkdir(parents=True)
    legacy.mkdir(parents=True)

    resolved = genie_tts_module._resolve_character_dir(settings, "baoqiao")

    assert resolved == preferred.resolve()


def test_resolve_character_dir_falls_back_to_gpt_sovits_root(tmp_path: Path) -> None:
    settings = SimpleNamespace(root=SimpleNamespace(root_dir=str(tmp_path)))
    legacy = tmp_path / "models" / "gptsovits" / "baoqiao"
    legacy.mkdir(parents=True)

    resolved = genie_tts_module._resolve_character_dir(settings, "baoqiao")

    assert resolved == legacy.resolve()


def test_resolve_genie_tts_resource_paths_prefers_geniedata_layout(tmp_path: Path) -> None:
    genie_data_dir = tmp_path / "models" / "geniedata"
    (genie_data_dir / "G2P" / "EnglishG2P").mkdir(parents=True)
    (genie_data_dir / "G2P" / "ChineseG2P").mkdir(parents=True)
    roberta_dir = genie_data_dir / "roberta-wwm-ext-large-onnx"
    roberta_dir.mkdir(parents=True)
    (roberta_dir / "model.onnx").write_bytes(b"onnx")
    (roberta_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

    settings = SimpleNamespace(root=SimpleNamespace(root_dir=str(tmp_path)))

    resources = genie_tts_module._resolve_genie_tts_resource_paths(settings)

    assert resources.genie_data_dir == genie_data_dir.resolve()
    assert resources.english_g2p_dir == (genie_data_dir / "G2P" / "EnglishG2P").resolve()
    assert resources.chinese_g2p_dir == (genie_data_dir / "G2P" / "ChineseG2P").resolve()
    assert resources.roberta_model_dir == roberta_dir.resolve()
    assert resources.roberta_model_path == (roberta_dir / "model.onnx").resolve()


def test_configure_genie_tts_environment_disables_auto_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    genie_data_dir = tmp_path / "models" / "geniedata"
    (genie_data_dir / "G2P" / "EnglishG2P").mkdir(parents=True)
    (genie_data_dir / "G2P" / "ChineseG2P").mkdir(parents=True)
    hubert_dir = genie_data_dir / "chinese-hubert-base"
    hubert_dir.mkdir(parents=True)
    (hubert_dir / "chinese-hubert-base.onnx").write_bytes(b"onnx")
    (hubert_dir / "chinese-hubert-base_weights_fp16.bin").write_bytes(b"bin")
    sv_model = genie_data_dir / "speaker_encoder.onnx"
    sv_model.write_bytes(b"onnx")
    roberta_dir = genie_data_dir / "roberta-wwm-ext-large-onnx"
    roberta_dir.mkdir(parents=True)
    (roberta_dir / "model.onnx").write_bytes(b"onnx")
    (roberta_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

    settings = SimpleNamespace(root=SimpleNamespace(root_dir=str(tmp_path)))
    spec = genie_tts_module.GenieTTSModelSpec(
        character_name="baoqiao",
        character_dir=tmp_path / "models" / "genie-tts" / "baoqiao",
        onnx_model_dir=tmp_path / "models" / "genie-tts" / "baoqiao" / "tts_models",
        language="Chinese",
        use_roberta=False,
    )

    monkeypatch.delenv("GENIE_DATA_DIR", raising=False)
    monkeypatch.delenv("GENIE_SKIP_RESOURCE_CHECK", raising=False)
    monkeypatch.delenv("English_G2P_DIR", raising=False)
    monkeypatch.delenv("Chinese_G2P_DIR", raising=False)
    monkeypatch.delenv("HUBERT_MODEL_DIR", raising=False)
    monkeypatch.delenv("SV_MODEL", raising=False)
    monkeypatch.delenv("ROBERTA_MODEL_DIR", raising=False)

    resources = genie_tts_module._configure_genie_tts_environment(settings, spec)

    assert resources.hubert_onnx_path == hubert_dir / "chinese-hubert-base.onnx"
    assert genie_tts_module.os.environ["GENIE_DATA_DIR"] == str(genie_data_dir)
    assert genie_tts_module.os.environ["GENIE_SKIP_RESOURCE_CHECK"] == "1"
    assert genie_tts_module.os.environ["English_G2P_DIR"] == str(genie_data_dir / "G2P" / "EnglishG2P")
    assert genie_tts_module.os.environ["Chinese_G2P_DIR"] == str(genie_data_dir / "G2P" / "ChineseG2P")
    assert genie_tts_module.os.environ["HUBERT_MODEL_DIR"] == str(hubert_dir)
    assert genie_tts_module.os.environ["SV_MODEL"] == str(sv_model)
    assert genie_tts_module.os.environ["ROBERTA_MODEL_DIR"] == str(roberta_dir)


def test_validate_genie_tts_resources_reports_missing_files(tmp_path: Path) -> None:
    settings = SimpleNamespace(root=SimpleNamespace(root_dir=str(tmp_path)))
    spec = genie_tts_module.GenieTTSModelSpec(
        character_name="baoqiao",
        character_dir=tmp_path / "models" / "genie-tts" / "baoqiao",
        onnx_model_dir=tmp_path / "models" / "genie-tts" / "baoqiao" / "tts_models",
        language="Chinese",
        use_roberta=True,
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        genie_tts_module._validate_genie_tts_resources(settings, spec)

    message = str(exc_info.value)
    assert "Automatic download is disabled here" in message
    assert "Chinese HuBERT ONNX" in message


def test_synthesize_once_waits_for_model_lock_without_blocking_event_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ref_audio = tmp_path / "ref.wav"
    ref_audio.write_bytes(b"fake")

    configured = genie_tts_module.GenieTTSModelSpec(
        character_name="baoqiao",
        character_dir=tmp_path / "models" / "genie-tts" / "baoqiao",
        onnx_model_dir=tmp_path / "models" / "genie-tts" / "baoqiao",
        language="Chinese",
        use_roberta=False,
    )

    class _FakeGenie:
        def set_reference_audio(self, **kwargs: object) -> None:
            del kwargs

        async def tts_async(self, **kwargs: object):
            del kwargs
            yield b"\x00\x00"

    monkeypatch.setattr(genie_tts_module, "_loaded_model_spec", configured)
    monkeypatch.setattr(genie_tts_module, "get_genie_tts_model", lambda: _FakeGenie())

    lock = genie_tts_module._model_lock
    acquired = lock.acquire(timeout=1.0)
    assert acquired

    async def run_test() -> None:
        synth_task = asyncio.create_task(
            genie_tts_module.synthesize_once(
                text="hello",
                ref_audio=ref_audio,
                ref_text="ref text",
            )
        )
        try:
            await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.1)
        finally:
            lock.release()
        wav_bytes = await asyncio.wait_for(synth_task, timeout=0.5)
        assert wav_bytes

    asyncio.run(run_test())


def test_stop_genie_tts_synthesis_calls_upstream_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    class _FakeGenie:
        def stop(self) -> None:
            nonlocal called
            called = True

    monkeypatch.setattr(genie_tts_module, "_genie_tts_module", _FakeGenie())

    genie_tts_module.stop_genie_tts_synthesis()

    assert called is True
