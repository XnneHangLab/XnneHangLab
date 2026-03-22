# pyright: reportUnknownVariableType=none, reportUnknownMemberType=none
# 在开头加入路径
from __future__ import annotations

import base64
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

# 从 packages/gpt_sovits 导入，实际上对应包里已经有了相关路由，只不过，再次定义是为了更清晰地看到和修改我们使用了哪些路由，以及方便定义 Client.
from lab.api.clients import GPTSoVITSRequest
from lab.utils.FFmpegHelper import file_to_mp3

if TYPE_CHECKING:
    from gsv.Synthesizers.base import Base_TTS_Task  # type: ignore[reportMissingImports]

# 创建合成器实例

router = APIRouter()


def _get_gsv_tts_state_manager():
    # Delay importing GSV until request handling so route registration stays side-effect free.
    state_manager_module = import_module("gsv.gsv_state_manager")
    return state_manager_module.gsv_tts_state_manager  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]


@router.post("/tts/gptsovits/character_list")
async def character_list(request: Request):
    tts_synthesizer = _get_gsv_tts_state_manager().get_tts_synthesizer()  # type: ignore[reportUnknownMemberType]
    if tts_synthesizer is None:
        return HTTPException(status_code=500, detail="TTS synthesizer not initialized")
    res = JSONResponse(tts_synthesizer.get_characters())  # type: ignore[reportUnknownMemberType]
    return res


@router.post("/tts/gptsovits")
async def gptsovits(request: Request) -> dict:  # type: ignore[reportUnknownParameterType,reportUnknownVariableType]
    # 尝试从JSON中获取数据，如果不是JSON，则从查询参数中获取
    data = await request.json()
    try:
        _request = GPTSoVITSRequest.model_validate(data)
    except Exception as e:
        return {"code": 500, "message": str(e)}
    tts_synthesizer = _get_gsv_tts_state_manager().get_tts_synthesizer()  # type: ignore[reportUnknownMemberType]
    if tts_synthesizer is None:
        return {"code": 500, "message": "TTS synthesizer not initialized"}
    task: Base_TTS_Task = tts_synthesizer.params_parser(data)  # type: ignore[reportUnknownMemberType]

    if task.task_type == "text" and task.text.strip() == "":  # type: ignore[reportUnknownMemberType]
        return {"code": 400, "message": "Text cannot be empty"}
    elif task.sample_rate is None:  # type: ignore[reportUnknownMemberType]
        return {"code": 400, "message": "Sample rate must be specified"}

    try:
        save_path = tts_synthesizer.generate(task, return_type="filepath")  # type: ignore[reportUnknownMemberType]
    except Exception as e:
        return {"code": 500, "message": f"Failed to generate audio: {e}"}
    if not isinstance(save_path, str):
        return {"code": 500, "message": "Failed to generate audio file"}
    # 转换 wav 文件为 mp3
    if _request.audio_type == "mp3":
        try:
            file_to_mp3(Path(save_path), Path(save_path).with_suffix(".mp3"))
        except Exception as e:
            return {"code": 500, "message": f"Failed to convert audio file to mp3: {str(e)}"}
    else:
        return {"code": 400, "message": f"Unsupported audio type: {_request.audio_type}"}
    with Path(save_path).with_suffix(f".{_request.audio_type}").open("rb") as f:
        bytes = f.read()
    sample_rate = task.sample_rate  # type: ignore[reportUnknownMemberType]
    return {
        "audio_byte": base64.b64encode(bytes).decode("utf-8"),
        "audio_rate": sample_rate,
        "audio_type": "mp3",
    }
