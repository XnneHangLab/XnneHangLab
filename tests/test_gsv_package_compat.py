from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from gsv.GPT_SoVITS.module.models import TextEncoder
from gsv.GPT_SoVITS.TTS_infer_pack.TTS import TTS
from gsv.Synthesizers.gsv_fast import gsv_config


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
