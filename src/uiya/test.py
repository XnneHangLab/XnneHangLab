import funasr
import torch
import torchaudio


def main():
    print(f"funasr:{funasr.__version__}")
    print(f"torch:{torch.__version__}")
    print(f"torchaudio:{torchaudio.__version__}")
