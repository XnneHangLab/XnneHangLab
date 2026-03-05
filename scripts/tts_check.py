#!/usr/bin/env python3
"""Check Qwen3-TTS Environment"""
import torch

print("🔍 Checking Qwen3-TTS environment...")
print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"CUDA version: {torch.version.cuda}")

try:
    from qwen_tts import Qwen3TTSModel
    print("✅ qwen_tts installed")
except ImportError as e:
    print(f"❌ qwen_tts not installed: {e}")
    print("   Run: pip install -e . (in Qwen3-TTS-streaming directory)")

try:
    import pyaudio
    print("✅ pyaudio installed")
except ImportError:
    print("⚠️  pyaudio not installed (optional, for tts-stream-play)")
    print("   Run: pip install pyaudio")

try:
    import soundfile
    print("✅ soundfile installed")
except ImportError:
    print("❌ soundfile not installed")
    print("   Run: pip install soundfile")
