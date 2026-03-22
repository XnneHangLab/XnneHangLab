# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownLambdaType=false, reportAttributeAccessIssue=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import torch
from gsv.GPT_SoVITS.module.models import TextEncoder
from gsv.GPT_SoVITS.TTS_infer_pack.TTS import TTS
from gsv.Synthesizers.gsv_fast import gsv_config
from gsv.Synthesizers.gsv_fast.GSV_Synthesizer import GSV_Synthesizer

if TYPE_CHECKING:
    from pathlib import Path


def test_load_infer_config_falls_back_to_infer_json(tmp_path: Path) -> None:
    infer_json = tmp_path / "infer.json"
    infer_json.write_text('{"gpt_path": "foo.ckpt", "sovits_path": "bar.pth"}', encoding="utf-8")

    config = gsv_config.load_infer_config(str(tmp_path))

    assert config["gpt_path"] == "foo.ckpt"
    assert config["sovits_path"] == "bar.pth"


def test_text_encoder_uses_v2_symbol_count() -> None:
    encoder = TextEncoder(
        out_channels=192,
        hidden_channels=192,
        filter_channels=768,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        version="v2",
    )

    assert encoder.text_embedding.num_embeddings == 732


def test_text_encoder_uses_v1_symbol_count() -> None:
    encoder = TextEncoder(
        out_channels=192,
        hidden_channels=192,
        filter_channels=768,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        version="v1",
    )

    assert encoder.text_embedding.num_embeddings == 322


def test_init_vits_weights_detects_v2_checkpoint(monkeypatch) -> None:
    captured = {}

    class FakeSynthesizerTrn:
        def __init__(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            self.enc_q = object()

        def to(self, device):
            captured["device"] = device
            return self

        def eval(self):
            captured["eval"] = True
            return self

        def load_state_dict(self, state_dict, strict=False):
            captured["state_dict"] = state_dict
            captured["strict"] = strict
            return None

    fake_checkpoint = {
        "config": {
            "data": {
                "filter_length": 2048,
                "sampling_rate": 32000,
                "hop_length": 640,
                "win_length": 2048,
                "n_speakers": 300,
            },
            "train": {"segment_size": 20480},
            "model": {
                "inter_channels": 192,
                "hidden_channels": 192,
                "filter_channels": 768,
                "n_heads": 2,
                "n_layers": 6,
                "kernel_size": 3,
                "p_dropout": 0.1,
                "resblock": "1",
                "resblock_kernel_sizes": [3, 7, 11],
                "resblock_dilation_sizes": [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
                "upsample_rates": [10, 8, 2, 2, 2],
                "upsample_initial_channel": 512,
                "upsample_kernel_sizes": [16, 16, 8, 2, 2],
                "gin_channels": 512,
                "n_layers_q": 3,
                "use_spectral_norm": False,
                "freeze_quantizer": True,
                "semantic_frame_rate": "25hz",
                "version": "v2",
            },
        },
        "weight": {
            "enc_p.text_embedding.weight": SimpleNamespace(shape=(732, 192)),
        },
    }

    monkeypatch.setattr("gsv.GPT_SoVITS.TTS_infer_pack.TTS.torch.load", lambda *args, **kwargs: fake_checkpoint)
    monkeypatch.setattr("gsv.GPT_SoVITS.TTS_infer_pack.TTS.SynthesizerTrn", FakeSynthesizerTrn)

    tts = object.__new__(TTS)
    tts.configs = SimpleNamespace(
        device="cpu",
        vits_weights_path="",
        save_configs=lambda: None,
        filter_length=0,
        segment_size=0,
        sampling_rate=0,
        hop_length=0,
        win_length=0,
        n_speakers=0,
        semantic_frame_rate="25hz",
        version="v1",
        update_version=lambda version: setattr(tts.configs, "version", version),
        is_half=False,
    )

    tts.init_vits_weights("fake-v2-model.pth")

    assert tts.configs.version == "v2"
    assert captured["kwargs"]["version"] == "v2"


def test_gsv_synthesizer_uses_conservative_defaults(tmp_path: Path) -> None:
    captured = {}
    ref_audio = tmp_path / "ref.wav"
    ref_audio.write_bytes(b"wav")

    synth = object.__new__(GSV_Synthesizer)
    synth.save_prompt_cache = False
    synth.prompt_cache_dir = "cache/prompt_cache"
    synth.tts_pipline = SimpleNamespace(run=lambda params: captured.setdefault("params", params))

    synth.get_wav_from_text_api(
        text="hello",
        ref_audio_path=str(ref_audio),
        prompt_text="hello",
        prompt_language="auto",
    )

    assert captured["params"]["parallel_infer"] is False
    assert captured["params"]["split_bucket"] is False


def test_tts_run_uses_serial_vits_decode_when_parallel_infer_disabled() -> None:
    decode_calls: list[tuple[tuple[int, ...], tuple[int, ...]]] = []

    class FakeModel:
        def infer_panel_0307(self, *args, **kwargs):
            return [
                torch.tensor([1, 2, 3], dtype=torch.long),
                torch.tensor([4, 5, 6], dtype=torch.long),
            ], [2, 2]

        infer_panel_batch_infer_with_flash_attn = infer_panel_0307

    class FakeVITS:
        upsample_rates = [2, 2]

        def decode(self, codes, text, refer):
            del refer
            decode_calls.append((tuple(codes.shape), tuple(text.shape)))
            return torch.ones((1, 1, 8), dtype=torch.float32)

    fake_batch = {
        "phones": [
            torch.tensor([1, 2, 3], dtype=torch.long),
            torch.tensor([4, 5], dtype=torch.long),
        ],
        "phones_len": torch.tensor([3, 2], dtype=torch.long),
        "all_phones": torch.tensor([[1, 2, 3], [4, 5, 0]], dtype=torch.long),
        "all_phones_len": torch.tensor([3, 2], dtype=torch.long),
        "all_bert_features": torch.zeros((2, 1024, 3), dtype=torch.float32),
        "norm_text": "hello",
        "max_len": 3,
    }

    tts = object.__new__(TTS)
    tts.configs = SimpleNamespace(
        sampling_rate=32000,
        device="cpu",
        languages=["auto", "zh", "ja", "en", "all_zh", "all_ja"],
        hz=50,
        max_sec=1,
    )
    tts.precision = torch.float32
    tts.prompt_cache = {
        "ref_audio_path": "dummy.wav",
        "prompt_semantic": torch.zeros((1, 4), dtype=torch.float32),
        "refer_spec": torch.zeros((1, 704, 3), dtype=torch.float32),
        "prompt_text": "hello",
        "prompt_lang": "auto",
        "phones": None,
        "bert_features": None,
        "norm_text": None,
    }
    tts.prompt_cache_path = ""
    tts.stop_flag = False
    tts.text_preprocessor = SimpleNamespace(preprocess=lambda *args, **kwargs: [{"dummy": True}])
    tts.to_batch = lambda *args, **kwargs: ([fake_batch], [0])
    tts.audio_postprocess = lambda *args, **kwargs: (32000, np.zeros(8, dtype=np.int16))
    tts.empty_cache = lambda: None
    tts.t2s_model = SimpleNamespace(model=FakeModel())
    tts.vits_model = FakeVITS()

    result = next(
        tts.run(
            {
                "text": "hello",
                "text_lang": "auto",
                "prompt_text": "hello",
                "prompt_lang": "auto",
                "ref_audio_path": "dummy.wav",
                "batch_size": 20,
                "parallel_infer": False,
                "split_bucket": False,
                "test_mode": True,
            }
        )
    )

    assert result[0] == 32000
    assert len(decode_calls) == 2
