"""Qwen3-TTS API Router - 仅负责 HTTP 请求/响应处理"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from lab.api.logic.qwen_tts_logic import get_logic

router = APIRouter()


@router.get("/tts/qwen/health")
async def health_check():
    """健康检查端点"""
    try:
        logic = get_logic()
        return logic.health_check()
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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
    import tempfile
    from pathlib import Path
    
    try:
        logic = get_logic()
        
        # 保存上传的参考音频到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(ref_audio.filename).suffix) as tmp:
            content = await ref_audio.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            audio_bytes, sr = logic.generate_voice_clone(
                text=text,
                language=language,
                ref_audio_path=tmp_path,
                ref_text=ref_text,
            )
            
            return Response(
                content=audio_bytes,
                media_type="audio/mpeg",
                headers={"Content-Disposition": "attachment; filename=tts_output.mp3"}
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
            
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
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
        logic = get_logic()
        
        result = logic.generate_voice_clone_base64(
            text=text,
            language=language,
            ref_audio_base64=ref_audio_base64,
            ref_text=ref_text,
        )
        
        return result
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
