#!/usr/bin/env python3
"""Qwen3-TTS Streaming TTS - 命令行工具"""
import sys
import argparse
import torch
import numpy as np
import soundfile as sf
from qwen_tts import Qwen3TTSModel


def main():
    parser = argparse.ArgumentParser(description='Qwen3-TTS Streaming TTS')
    parser.add_argument('--text', type=str, required=True, help='要合成的文本')
    parser.add_argument('--ref-audio', type=str, required=True, help='参考音频路径')
    parser.add_argument('--ref-text', type=str, required=True, help='参考音频文本')
    parser.add_argument('--output', type=str, default='output_streaming.wav', help='输出文件')
    parser.add_argument('--language', type=str, default='Auto', help='语言')
    parser.add_argument('--emit-every', type=int, default=4, help='每 N 帧输出一次')
    parser.add_argument('--decode-window', type=int, default=80, help='解码窗口大小')
    args = parser.parse_args()

    print("🎤 Qwen3-TTS Streaming TTS")
    print(f"Text: {args.text}")
    print(f"Reference: {args.ref_audio}")
    print(f"Output: {args.output}")

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

    # 流式生成
    print("Generating...")
    chunks = []
    sr = 24000
    first_chunk_time = None
    import time
    start_time = time.time()

    for chunk, chunk_sr in model.stream_generate_voice_clone(
        text=args.text,
        language=args.language,
        voice_clone_prompt={
            'ref_audio': args.ref_audio,
            'ref_text': args.ref_text
        },
        emit_every_frames=args.emit_every,
        decode_window_frames=args.decode_window,
        overlap_samples=0,
    ):
        if first_chunk_time is None:
            first_chunk_time = time.time() - start_time
            print(f"First chunk: {first_chunk_time*1000:.0f}ms")
        chunks.append(chunk)
        sr = chunk_sr

    total_time = time.time() - start_time
    audio = np.concatenate(chunks) if chunks else np.array([])
    audio_duration = len(audio) / sr if sr > 0 else 0
    rtf = total_time / audio_duration if audio_duration > 0 else 0

    # 保存文件
    sf.write(args.output, audio, sr)
    
    print(f"✅ Saved to {args.output}")
    print(f"   Audio duration: {audio_duration:.2f}s")
    print(f"   Total time: {total_time:.2f}s")
    print(f"   RTF: {rtf:.2f} ({1/rtf:.1f}x real-time)")


if __name__ == "__main__":
    main()
