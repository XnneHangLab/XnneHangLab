"""Qwen3-TTS 业务逻辑层 - 与 FastAPI Router 分离"""
from __future__ import annotations

import base64
import tempfile
from io import BytesIO
from pathlib import Path

import soundfile as sf
import torch
from loguru import logger
from qwen_tts import Qwen3TTSModel


class QwenTTSLogic:
    """Qwen3-TTS 业务逻辑类"""
    
    def __init__(self, model_path: str):
        self.model_path = Path(model_path)
        self._model: Qwen3TTSModel | None = None
    
    @property
    def model(self) -> Qwen3TTSModel:
        """懒加载模型实例"""
        if self._model is None:
            logger.info(f"Loading Qwen3-TTS model from {self.model_path}...")
            
            # 注意力实现：优先 sdpa（PyTorch 2.x 内置），兼容 Windows/无 GPU 环境
            attn_impl = "sdpa"  # 可选：sdpa / eager / auto / flash_attention_2
            
            if torch.cuda.is_available():
                device_map = "cuda:0"
                dtype = torch.bfloat16
                logger.info(f"Using GPU with attn_implementation={attn_impl}")
            else:
                device_map = "cpu"
                dtype = torch.float32
                logger.warning("GPU not available, using CPU (slow)")
            
            self._model = Qwen3TTSModel.from_pretrained(
                str(self.model_path),
                device_map=device_map,
                dtype=dtype,
                attn_implementation=attn_impl,
            )
            logger.info("Qwen3-TTS model loaded successfully")
        
        return self._model
    
    def health_check(self) -> dict:
        """健康检查"""
        return {
            "status": "healthy" if self._model is not None else "not_loaded",
            "model_loaded": self._model is not None,
            "cuda_available": torch.cuda.is_available(),
        }
    
    def generate_voice_clone(
        self,
        text: str,
        language: str,
        ref_audio_path: str,
        ref_text: str,
    ) -> tuple[bytes, int]:
        """
        生成语音克隆
        
        Returns:
            (audio_bytes, sample_rate) - MP3 格式的音频数据和采样率
        """
        logger.info(f"Generating TTS for text: {text[:50]}...")
        
        wavs, sr = self.model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=ref_audio_path,
            ref_text=ref_text,
        )
        
        # 转换为 MP3 格式
        buffer = BytesIO()
        sf.write(buffer, wavs[0], sr, format='mp3')
        buffer.seek(0)
        
        return buffer.read(), sr
    
    def generate_voice_clone_base64(
        self,
        text: str,
        language: str,
        ref_audio_base64: str,
        ref_text: str,
    ) -> dict:
        """
        生成语音克隆（base64 输入/输出）
        
        Returns:
            {
                "audio_base64": str,
                "sample_rate": int,
                "format": "mp3"
            }
        """
        # 解码 base64 音频
        try:
            audio_data = base64.b64decode(ref_audio_base64)
        except Exception as e:
            raise ValueError(f"Invalid base64 audio: {e}")
        
        # 保存为临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            audio_bytes, sr = self.generate_voice_clone(
                text=text,
                language=language,
                ref_audio_path=tmp_path,
                ref_text=ref_text,
            )
            
            return {
                "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                "sample_rate": sr,
                "format": "mp3",
            }
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# 全局单例（懒加载）
_logic: QwenTTSLogic | None = None


def get_logic() -> QwenTTSLogic:
    """获取 QwenTTSLogic 单例"""
    global _logic
    
    if _logic is None:
        from pathlib import Path
        from lab.config_manager import load_settings_file, XnneHangLabSettings
        
        # 从 lab.toml 读取项目根目录（abs_root.py 已设置为绝对路径）
        try:
            lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
            root_dir = Path(lab_settings.root.root_dir)
        except Exception as e:
            # 回退：从 __file__ 向上查找 5 层（src/lab/api/logic -> project root）
            root_dir = Path(__file__).parent.parent.parent.parent.parent
        
        model_path = root_dir / "models" / "qwen-tts" / "Qwen3-TTS-12Hz-1.7B-Base"
        
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}. Run `just install-qwen-tts` to download the model."
            )
        
        _logic = QwenTTSLogic(str(model_path))
    
    return _logic
