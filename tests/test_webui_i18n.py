from __future__ import annotations

import pytest

from lab.config_manager.i18n import ASRModelProvider, Device, I18nEnum


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


@pytest.mark.parametrize(
    ("member", "expected_name", "expected_label"),
    [
        (Device.cpu, "cpu", "cpu"),
        (Device.cuda, "cuda", "gpu"),
        (ASRModelProvider.qwen, "qwen", "Qwen3-ASR"),
        (ASRModelProvider.sherpa, "sherpa", "Sherpa-ONNX Paraformer"),
    ],
)
def test_enum_name_and_label(member: I18nEnum, expected_name: str, expected_label: str) -> None:
    assert member.name == expected_name
    assert member.value == expected_label


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
