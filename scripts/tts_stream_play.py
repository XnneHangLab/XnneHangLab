#!/usr/bin/env python3
"""Qwen3-TTS Streaming + Real-time Playback"""
import sys
import argparse
import torch
import numpy as np

try:
    import pyaudio as pa
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("❌ pyaudio not installed. Run: pip install pyaudio")
    sys.exit(1)

from qwen_tts import Qwen3TTSModel


def main():
    parser = argparse.ArgumentParser(description='Qwen3-TTS Streaming + Playback')
    parser.add_argument('--text', type=str, required=True, help='要合成的文本')
    parser.add_argument('--ref-audio', type=str, required=True, help='参考音频路径')
    parser.add_argument('--ref-text', type=str, required=True, help='参考音频文本')
    parser.add_argument('--language', type=str, default='Auto', help='语言')
    parser.add_argument('--emit-every', type=int, default=4, help='每 N 帧输出一次')
    args = parser.parse_args()

    if not PYAUDIO_AVAILABLE:
        sys.exit(1)

    print("🎤 Qwen3-TTS Streaming + Playback")
    print(f"Text: {args.text}")
    print(f"Reference: {args.ref_audio}")

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

    # 初始化音频流
    p = pa.PyAudio()
    sample_rate = 24000
    stream = p.open(
        format=pa.paFloat32,
        channels=1,
        rate=sample_rate,
        output=True,
    )

    # 流式生成并播放
    print("Streaming...")
    chunk_count = 0
    first_chunk_time = None
    import time
    start_time = time.time()

    try:
        for chunk, sr in model.stream_generate_voice_clone(
            text=args.text,
            language=args.language,
            voice_clone_prompt={
                'ref_audio': args.ref_audio,
                'ref_text': args.ref_text
            },
            emit_every_frames=args.emit_every,
            decode_window_frames=80,
            overlap_samples=0,
        ):
            if first_chunk_time is None:
                first_chunk_time = time.time() - start_time
                print(f"First chunk: {first_chunk_time*1000:.0f}ms")
            
            # 播放音频块
            stream.write(chunk.astype(np.float32).tobytes())
            chunk_count += 1

        total_time = time.time() - start_time
        print(f"✅ Done")
        print(f"   Chunks: {chunk_count}")
        print(f"   Total time: {total_time:.2f}s")
        if first_chunk_time:
            print(f"   First chunk latency: {first_chunk_time*1000:.0f}ms")

    except KeyboardInterrupt:
        print("\n⚠️ Interrupted")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    main()
