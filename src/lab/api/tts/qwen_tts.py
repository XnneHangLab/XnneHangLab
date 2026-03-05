"""Qwen3-TTS API Router - 支持语音克隆的 TTS 服务"""
from __future__ import annotations

import base64
import tempfile
from io import BytesIO
from pathlib import Path

import soundfile as sf
import torch
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from loguru import logger
from qwen_tts import Qwen3TTSModel

router = APIRouter()

# 全局模型实例（懒加载）
_model: Qwen3TTSModel | None = None
_model_path: str | None = None


def get_model(model_path: str) -> Qwen3TTSModel:
    """获取或初始化 Qwen3-TTS 模型实例"""
    global _model, _model_path
    
    if _model is None or _model_path != model_path:
        logger.info(f"Loading Qwen3-TTS model from {model_path}...")
        
        # 检测 GPU 可用性
        if torch.cuda.is_available():
            device_map = "cuda:0"
            dtype = torch.bfloat16
            attn_impl = "flash_attention_2"
            logger.info("Using GPU with FlashAttention 2")
        else:
            device_map = "cpu"
            dtype = torch.float32
            attn_impl = "eager"
            logger.warning("GPU not available, using CPU (slow)")
        
        _model = Qwen3TTSModel.from_pretrained(
            model_path,
            device_map=device_map,
            dtype=dtype,
            attn_implementation=attn_impl,
        )
        _model_path = model_path
        logger.info("Qwen3-TTS model loaded successfully")
    
    return _model


@router.post("/tts/qwen/health")
async def health_check():
    """健康检查端点"""
    global _model
    return {
        "status": "healthy" if _model is not None else "not_loaded",
        "model_loaded": _model is not None,
        "cuda_available": torch.cuda.is_available(),
    }


@router.post("/tts/qwen/clone")
async def voice_clone(
    text: str = Form(..., description="要合成的文本"),
    language: str = Form("Chinese", description="语言（Chinese/English/Japanese/Korean 等）"),
    ref_audio: UploadFile = File(..., description="参考音频文件（用于语音克隆）"),
    ref_text: str = Form(..., description="参考音频的文本内容"),
):
    """
    语音克隆 TTS - 使用参考音频克隆声音并合成新文本
    
    支持格式：wav, mp3, flac, ogg 等
    参考音频建议：3-10 秒清晰的人声
    """
    try:
        # 验证模型已加载
        model_path = Path(__file__).parent.parent.parent.parent / "models" / "qwen-tts" / "Qwen3-TTS-12Hz-1.7B-Base"
        if not model_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Model not found at {model_path}. Run `just install-qwen-tts` first."
            )
        
        model = get_model(str(model_path))
        
        # 保存上传的参考音频到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(ref_audio.filename).suffix) as tmp:
            content = await ref_audio.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # 生成语音
            logger.info(f"Generating TTS for text: {text[:50]}...")
            wavs, sr = model.generate_voice_clone(
                text=text,
                language=language,
                ref_audio=tmp_path,
                ref_text=ref_text,
            )
            
            # 转换为 MP3 格式并返回
            buffer = BytesIO()
            sf.write(buffer, wavs[0], sr, format='mp3')
            buffer.seek(0)
            
            return Response(
                content=buffer.read(),
                media_type="audio/mpeg",
                headers={"Content-Disposition": "attachment; filename=tts_output.mp3"}
            )
            
        finally:
            # 清理临时文件
            Path(tmp_path).unlink(missing_ok=True)
            
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tts/qwen/clone_base64")
async def voice_clone_base64(
    text: str = Form(..., description="要合成的文本"),
    language: str = Form("Chinese", description="语言"),
    ref_audio_base64: str = Form(..., description="参考音频的 base64 编码"),
    ref_text: str = Form(..., description="参考音频的文本内容"),
):
    """
    语音克隆 TTS（base64 版本）- 适合通过 JSON 调用
    
    ref_audio_base64: base64 编码的音频数据（支持 wav/mp3 等）
    """
    try:
        # 验证模型已加载
        model_path = Path(__file__).parent.parent.parent.parent / "models" / "qwen-tts" / "Qwen3-TTS-12Hz-1.7B-Base"
        if not model_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Model not found at {model_path}. Run `just install-qwen-tts` first."
            )
        
        model = get_model(str(model_path))
        
        # 解码 base64 音频
        try:
            audio_data = base64.b64decode(ref_audio_base64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {e}")
        
        # 保存为临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            # 生成语音
            logger.info(f"Generating TTS for text: {text[:50]}...")
            wavs, sr = model.generate_voice_clone(
                text=text,
                language=language,
                ref_audio=tmp_path,
                ref_text=ref_text,
            )
            
            # 转换为 base64 返回
            buffer = BytesIO()
            sf.write(buffer, wavs[0], sr, format='mp3')
            buffer.seek(0)
            audio_base64 = base64.b64encode(buffer.read()).decode("utf-8")
            
            return {
                "audio_base64": audio_base64,
                "sample_rate": sr,
                "format": "mp3",
            }
            
        finally:
            Path(tmp_path).unlink(missing_ok=True)
            
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
