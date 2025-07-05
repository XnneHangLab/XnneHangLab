# 在开头加入路径
from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

# 从 packages/gpt_sovits 导入，实际上对应包里已经有了相关路由，只不过，再次定义是为了更清晰地看到和修改我们使用了哪些路由，以及方便定义 Client.
from gsv.gsv_state_manager import gsv_tts_state_manager

from lab.utils.FFmpegHelper import file_to_mp3

if TYPE_CHECKING:
    from gsv.Synthesizers.base import Base_TTS_Task

# 创建合成器实例

router = APIRouter()


@router.post("/tts/gptsovits/character_list")
async def character_list(request: Request):
    tts_synthesizer = gsv_tts_state_manager.get_tts_synthesizer()
    if tts_synthesizer is None:
        return HTTPException(status_code=500, detail="TTS synthesizer not initialized")
    res = JSONResponse(tts_synthesizer.get_characters())
    return res


# {
#     "method": "POST",
#     "body": {
#         "character": "${chaName}",
#         "emotion": "${Emotion}",
#         "text": "${speakText}",
#         "ref_audio_path": "${refAudioPath}",
#         "text_language": "${textLanguage}",
#         "batch_size": ${batch_size},
#         "speed": ${speed},
#         "top_k": ${topK},
#         "top_p": ${topP},
#         "temperature": ${temperature},
#         "stream": "${stream}",
#         "format": "${Format}",
#         "save_temp": "${saveTemp}"
#     }
# }


@router.post("/tts/gptsovits")
async def tts(request: Request):
    # 尝试从JSON中获取数据，如果不是JSON，则从查询参数中获取
    if request.method == "GET":
        data = request.query_params
    else:
        data = await request.json()
    tts_synthesizer = gsv_tts_state_manager.get_tts_synthesizer()
    if tts_synthesizer is None:
        return HTTPException(status_code=500, detail="TTS synthesizer not initialized")
    task: Base_TTS_Task = tts_synthesizer.params_parser(data)  # type: ignore

    if task.task_type == "text" and task.text.strip() == "":  # type: ignore
        return HTTPException(status_code=400, detail="Text is empty")
    elif task.task_type == "ssml" and task.ssml.strip() == "":  # type: ignore
        return HTTPException(status_code=400, detail="SSML is empty")
    elif task.sample_rate is None:
        return HTTPException(status_code=400, detail="Sample rate is not specified")
    try:
        save_path = tts_synthesizer.generate(task, return_type="filepath")  # type: ignore
        if not isinstance(save_path, str):
            return HTTPException(status_code=500, detail="Failed to generate audio file")
    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))
    # 转换 wav 文件为 opus
    try:
        file_to_mp3(Path(save_path), Path(save_path).with_suffix(".mp3"))  # type: ignore
    except Exception as e:
        return HTTPException(status_code=500, detail=f"Error converting file to opus: {str(e)}")
    with Path(save_path).with_suffix(".mp3").open("rb") as f:
        mp3_bytes = f.read()
    sample_rate = task.sample_rate
    return {
        "audio_byte": base64.b64encode(mp3_bytes).decode("utf-8"),
        "audio_rate": sample_rate,
        "audio_type": "mp3",
    }
