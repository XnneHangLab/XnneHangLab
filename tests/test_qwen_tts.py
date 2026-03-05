#!/usr/bin/env python3
"""测试 Qwen3-TTS 语音克隆功能"""

import base64
import requests

# API 端点
BASE_URL = "http://localhost:12393"
CLONE_URL = f"{BASE_URL}/tts/qwen/clone_base64"
HEALTH_URL = f"{BASE_URL}/tts/qwen/health"


def check_health():
    """检查服务健康状态"""
    print("🔍 检查服务健康状态...")
    resp = requests.get(HEALTH_URL)
    print(f"响应：{resp.json()}")
    return resp.json()


def test_clone_with_audio_file():
    """使用音频文件测试语音克隆（需要本地音频文件）"""
    print("\n🎤 测试语音克隆（文件上传方式）...")
    
    # 准备参考音频（需要替换成实际文件）
    ref_audio_path = "./examples/example3.opus"  # 替换为你的参考音频
    
    try:
        with open(ref_audio_path, "rb") as f:
            audio_data = f.read()
        
        files = {
            "ref_audio": ("ref.wav", audio_data, "audio/wav"),
        }
        data = {
            "text": "你好，这是使用 Qwen3-TTS 生成的语音克隆测试。",
            "language": "Chinese",
            "ref_text": "这是参考音频的文本内容，需要和参考音频匹配。",
        }
        
        resp = requests.post(f"{BASE_URL}/tts/qwen/clone", files=files, data=data)
        
        if resp.status_code == 200:
            with open("output_clone.mp3", "wb") as f:
                f.write(resp.content)
            print("✅ 成功！输出文件：output_clone.mp3")
        else:
            print(f"❌ 失败：{resp.status_code} - {resp.text}")
            
    except FileNotFoundError:
        print(f"⚠️  参考音频文件不存在：{ref_audio_path}")
        print("   请先准备一个参考音频文件（3-10 秒清晰人声）")


def test_clone_base64():
    """使用 base64 编码测试语音克隆"""
    print("\n🎤 测试语音克隆（base64 方式）...")
    
    # 准备参考音频（需要替换成实际文件）
    ref_audio_path = "./examples/example3.opus"
    
    try:
        with open(ref_audio_path, "rb") as f:
            audio_data = f.read()
        
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        
        data = {
            "text": "你好，这是使用 Qwen3-TTS 生成的语音克隆测试。",
            "language": "Chinese",
            "ref_audio_base64": audio_base64,
            "ref_text": "这是参考音频的文本内容，需要和参考音频匹配。",
        }
        
        resp = requests.post(CLONE_URL, data=data)
        
        if resp.status_code == 200:
            result = resp.json()
            output_audio = base64.b64decode(result["audio_base64"])
            with open("output_clone_base64.mp3", "wb") as f:
                f.write(output_audio)
            print(f"✅ 成功！输出文件：output_clone_base64.mp3")
            print(f"   采样率：{result['sample_rate']}")
        else:
            print(f"❌ 失败：{resp.status_code} - {resp.text}")
            
    except FileNotFoundError:
        print(f"⚠️  参考音频文件不存在：{ref_audio_path}")


if __name__ == "__main__":
    print("=" * 60)
    print("Qwen3-TTS 测试脚本")
    print("=" * 60)
    
    # 1. 检查健康状态
    health = check_health()
    
    if not health.get("model_loaded"):
        print("\n⚠️  模型未加载！请先启动服务器并确保 qwen_tts = true")
        print("   运行：uv run run_server.py")
        exit(1)
    
    # 2. 测试语音克隆
    test_clone_base64()
    # test_clone_with_audio_file()  # 如果需要测试文件上传方式
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
