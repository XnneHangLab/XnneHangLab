from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

import lab.api.routes.gsv_lite as gsv_lite_route

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_generate_returns_json_error_response_on_unexpected_exception(monkeypatch: MonkeyPatch) -> None:
    async def fake_synthesize_once(**_kwargs: object) -> bytes:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        gsv_lite_route,
        "_get_gsv_lite_logic_module",
        lambda: SimpleNamespace(synthesize_once=fake_synthesize_once, get_sample_rate=lambda: 32000),
    )

    response = asyncio.run(
        gsv_lite_route.generate(
            gsv_lite_route.GSVLiteGeneratePayload(
                text="test",
                ref_audio_path="models/gsv-tts-lite/luoqixi/emotions/そ、そんな呼び方をして、慣れ慣れ思考はありませんか.wav",
                ref_text="test ref",
            )
        )
    )

    assert response.status_code == 500
    assert json.loads(bytes(response.body)) == {"error": "boom"}
