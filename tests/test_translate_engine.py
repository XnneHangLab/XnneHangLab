from __future__ import annotations

from lab.translate.engine import LLMTranslateEngine


def test_build_system_prompt_for_japanese_forbids_simplified_chinese() -> None:
    prompt = LLMTranslateEngine._build_system_prompt("JA")

    assert "natural Japanese" in prompt
    assert "Do not include Simplified Chinese characters" in prompt
    assert "Output translation only." in prompt


def test_build_system_prompt_for_non_japanese_stays_minimal() -> None:
    prompt = LLMTranslateEngine._build_system_prompt("ZH")

    assert prompt == "Translate to Chinese. Output translation only."
