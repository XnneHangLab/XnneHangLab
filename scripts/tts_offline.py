#!/usr/bin/env python3
"""Qwen3-TTS Offline TTS - 命令行工具"""
import sys
import argparse
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel


def main():
    parser = argparse.ArgumentParser(description='Qwen3-TTS Offline TTS')
    parser.add_argument('--text', type=str, required=True, help='要合成的文本')
    parser.add_argument('--ref-audio', type=str, required=True, help='参考音频路径')
    parser.add_argument('--ref-text', type=str, required=True, help='参考音频文本')
    parser.add_argument('--output', type=str, default='output_offline.wav', help='输出文件')
    parser.add_argument('--language', type=str, default='Auto', help='语言')
    args = parser.parse_args()

    print("🎤 Qwen3-TTS Offline TTS")
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

    # 生成
    print("Generating...")
    wavs, sr = model.generate_voice_clone(
        text=args.text,
        language=args.language,
        ref_audio=args.ref_audio,
        ref_text=args.ref_text,
    )

    # 保存文件
    sf.write(args.output, wavs[0], sr)
    
    audio_duration = len(wavs[0]) / sr
    print(f"✅ Saved to {args.output}")
    print(f"   Audio duration: {audio_duration:.2f}s")


if __name__ == "__main__":
    main()
