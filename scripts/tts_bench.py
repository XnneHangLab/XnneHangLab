#!/usr/bin/env python3
"""Qwen3-TTS Performance Benchmark"""
import time
import torch
import numpy as np
from qwen_tts import Qwen3TTSModel


def main():
    print("⚡ Qwen3-TTS Performance Benchmark")
    print("=" * 60)

    # 设备选择
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    print(f"Device: {device}, Dtype: {dtype}")

    # 加载模型
    print("Loading model...")
    model = Qwen3TTSModel.from_pretrained(
        'Qwen/Qwen3-TTS-12Hz-1.7B-Base',
        device_map=device,
        dtype=dtype,
        attn_implementation='sdpa',
    )

    # 测试文本
    text = 'これはテストです。こんにちは、お元気ですか？'
    ref_audio = './examples/elaina_example.wav'
    ref_text = 'テスト'

    # Warmup
    print("Warmup...")
    model.generate_voice_clone(
        text='テスト',
        language='Auto',
        ref_audio=ref_audio,
        ref_text=ref_text,
    )

    # 流式测试
    print("Testing streaming...")
    start = time.time()
    chunks = []
    sr = 24000
    first_chunk_time = None

    for chunk, chunk_sr in model.stream_generate_voice_clone(
        text=text,
        language='Auto',
        voice_clone_prompt={
            'ref_audio': ref_audio,
            'ref_text': ref_text
        },
        emit_every_frames=4,
        decode_window_frames=80,
        overlap_samples=0,
    ):
        if first_chunk_time is None:
            first_chunk_time = time.time() - start
        chunks.append(chunk)
        sr = chunk_sr

    total = time.time() - start
    audio = np.concatenate(chunks) if chunks else np.array([])
    dur = len(audio) / sr if sr > 0 else 0
    rtf = total / dur if dur > 0 else 0

    print("=" * 60)
    print(f"First chunk: {first_chunk_time*1000:.0f}ms")
    print(f"Total: {total:.2f}s, Audio: {dur:.2f}s, RTF: {rtf:.2f}")
    print(f"Speedup: {1/rtf:.1f}x real-time")
    print("=" * 60)


if __name__ == "__main__":
    main()
