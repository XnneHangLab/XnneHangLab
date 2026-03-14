from __future__ import annotations

import pytest

from lab.config_manager.asr import ASRSettings
from lab.config_manager.audio_recognize import AudioRecognizeSettings
from lab.streamlit.i18n import ASRModelProvider, Device, Guide, I18nEnum, SubtitleSpeed


def test_labels_returns_display_values() -> None:
    assert Device.labels() == ["cpu", "gpu"]


def test_names_returns_english_keys() -> None:
    assert Device.names() == ["cpu", "cuda"]


def test_from_name_returns_correct_member() -> None:
    assert Device.from_name("cpu") is Device.cpu
    assert Device.from_name("cuda") is Device.cuda


def test_from_name_raises_on_unknown_key() -> None:
    with pytest.raises(ValueError, match="未知英文 key"):
        Device.from_name("tpu")


def test_get_index_returns_position() -> None:
    assert Device.cpu.get_index() == 0
    assert Device.cuda.get_index() == 1


def test_get_index_three_members() -> None:
    assert SubtitleSpeed.slow.get_index() == 0
    assert SubtitleSpeed.normal.get_index() == 1
    assert SubtitleSpeed.fast.get_index() == 2


@pytest.mark.parametrize(
    ("member", "expected_name", "expected_label"),
    [
        (Device.cpu, "cpu", "cpu"),
        (Device.cuda, "cuda", "gpu"),
        (Guide.open, "open", "开启"),
        (Guide.close, "close", "关闭"),
        (SubtitleSpeed.slow, "slow", "慢"),
        (SubtitleSpeed.normal, "normal", "正常"),
        (SubtitleSpeed.fast, "fast", "快"),
        (ASRModelProvider.qwen, "qwen", "Qwen3-ASR"),
        (ASRModelProvider.sherpa, "sherpa", "Sherpa-ONNX Paraformer"),
    ],
)
def test_enum_name_and_label(member: I18nEnum, expected_name: str, expected_label: str) -> None:
    assert member.name == expected_name
    assert member.value == expected_label


def test_get_labels_returns_correct_options() -> None:
    settings = ASRSettings()  # pyright: ignore[reportCallIssue]
    assert settings.get_labels("device") == ["cpu", "gpu"]
    assert settings.get_labels("asr_model_provider") == ["Qwen3-ASR", "Sherpa-ONNX Paraformer"]


def test_get_index_reflects_current_value() -> None:
    settings = ASRSettings()  # pyright: ignore[reportCallIssue]
    assert settings.get_index("device") == 0
    assert settings.get_index("asr_model_provider") == 0


def test_set_by_label_updates_field() -> None:
    settings = ASRSettings()  # pyright: ignore[reportCallIssue]
    settings.set_by_label("device", "gpu")
    assert settings.device == "cuda"
    settings.set_by_label("asr_model_provider", "Sherpa-ONNX Paraformer")
    assert settings.asr_model_provider == "sherpa"


def test_set_by_label_unknown_label_raises() -> None:
    settings = ASRSettings()  # pyright: ignore[reportCallIssue]
    with pytest.raises(ValueError, match="不存在 label"):
        settings.set_by_label("device", "tpu")


def test_get_index_unregistered_field_raises() -> None:
    settings = ASRSettings()  # pyright: ignore[reportCallIssue]
    with pytest.raises(ValueError, match="未在 _I18N_FIELDS"):
        settings.get_index("cache_dir")


def test_audio_recognize_settings_i18n() -> None:
    settings = AudioRecognizeSettings()  # pyright: ignore[reportCallIssue]
    assert settings.get_labels("guide") == ["开启", "关闭"]
    assert settings.get_index("guide") == 0
    settings.set_by_label("guide", "关闭")
    assert settings.guide == "close"
    assert settings.get_index("guide") == 1
