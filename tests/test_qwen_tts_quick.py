#!/usr/bin/env python3
"""Qwen3-TTS 快速测试脚本 - 用于 just test-qwen-tts"""
import sys
import base64
import requests
import json

def main():
    if len(sys.argv) < 4:
        print("Usage: python test_qwen_tts_quick.py <ref_audio> <text> <ref_text>")
        sys.exit(1)
    
    ref_audio = sys.argv[1]
    text = sys.argv[2]
    ref_text = sys.argv[3]
    
    # 编码音频
    print("Encoding audio to base64...")
    with open(ref_audio, 'rb') as f:
        audio_b64 = base64.b64encode(f.read()).decode()
    
    # 发送请求
    print("Sending request to /tts/qwen/clone_base64...")
    resp = requests.post(
        'http://127.0.0.1:12393/tts/qwen/clone_base64',
        data={
            'text': text,
            'language': 'Chinese',
            'ref_audio_base64': audio_b64,
            'ref_text': ref_text
        }
    )
    
    print(f"Status: {resp.status_code}")
    result = resp.json()
    print("Response:", json.dumps(result, indent=2, ensure_ascii=False))
    
    if resp.status_code != 200:
        print(f"❌ Request failed: {result}")
        sys.exit(1)
    
    # 保存音频
    if 'audio_base64' in result:
        audio_data = base64.b64decode(result['audio_base64'])
        with open('qwen_output.mp3', 'wb') as f:
            f.write(audio_data)
        print("✅ Output saved to qwen_output.mp3")
    else:
        print(f"❌ No audio_base64 in response: {result}")
        sys.exit(1)

if __name__ == "__main__":
    main()
