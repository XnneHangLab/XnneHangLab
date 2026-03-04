from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from gsv.gsv_state_manager import gsv_tts_state_manager  # type: ignore[reportMissingImports,reportUnknownVariableType]
from loguru import logger

from lab.utils.FFmpegHelper import file_to_mp3

if TYPE_CHECKING:
    from collections.abc import Generator

router = APIRouter()

REF_AUDIO_BASE_DIR = Path("./models/gptsovits/elaina").resolve()


def _resolve_ref_audio_path(p: str) -> str:
    """
    解析 ref_audio_path，确保它是绝对路径，且在 REF_AUDIO_BASE_DIR 下。
    """
    cand = Path(p)
    if not cand.is_absolute():
        cand = (REF_AUDIO_BASE_DIR / cand).resolve()
    else:
        cand = cand.resolve()
    if REF_AUDIO_BASE_DIR not in cand.parents and cand != REF_AUDIO_BASE_DIR:
        raise HTTPException(status_code=400, detail="Invalid ref_audio_path (out of base dir)")
    if not cand.exists():
        raise HTTPException(status_code=404, detail=f"ref_audio_path not found: {cand}")
    return str(cand)


async def _read_request_data(request: Request) -> dict[str, Any]:
    """
    WebAPI v2 主要是 GET query；但也兼容 POST(json / form) 以防你后面还要复用。
    """
    if request.method == "GET":
        return dict(request.query_params)

    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            return await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}") from e

    if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
        form = await request.form()
        return dict(form)

    # fallback：允许 query 兜底
    return dict(request.query_params)


def _normalize_webapi_v2_params(data: dict[str, Any]) -> dict[str, Any]:
    """
    把 WebAPI v2 参数名对齐到你内部可能用到的字段名。
    - WebAPI v2: text_lang / prompt_lang
    - 你现有：可能有 text_language / prompt_language
    """
    d = dict(data)

    # 兼容 text_lang / text_language
    if "text_lang" in d and "text_language" not in d:
        d["text_language"] = d["text_lang"]
    if "text_language" in d and "text_lang" not in d:
        d["text_lang"] = d["text_language"]

    # 兼容 prompt_lang / prompt_language
    if "prompt_lang" in d and "prompt_language" not in d:
        d["prompt_language"] = d["prompt_lang"]
    if "prompt_language" in d and "prompt_lang" not in d:
        d["prompt_lang"] = d["prompt_language"]

    # ref_audio_path：建议转成绝对/安全路径（按你需要可移除这行）
    if "ref_audio_path" in d and isinstance(d["ref_audio_path"], str) and d["ref_audio_path"].strip():
        d["ref_audio_path"] = _resolve_ref_audio_path(d["ref_audio_path"].strip())

    # 默认值
    d.setdefault("speed_factor", 1.0)
    d.setdefault("streaming_mode", False)

    # WebAPI v2 默认输出 wav（AIChat README 也是下载 tts.wav）:contentReference[oaicite:2]{index=2}
    d.setdefault("audio_type", "wav")

    return d


def _iter_file(path: Path, chunk_size: int = 1024 * 256) -> Generator[bytes, None, None]:
    """
    按 chunk_size 读取文件内容，返回字节流。
    """
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


# 我为什么又写上了 /tts?
# 因为 https://github.com/qzrs777/AIChat
# 它的最终接口硬拼凑了一个 /tts 路径。暂时这么写，等我大改 Mod 的时候就会顺便修改掉那个硬拼的内容。
@router.get("/tts/gptsovitsv2/tts")
@router.post("/tts/gptsovitsv2/tts")
async def tts_webapi_v2_compat(request: Request, background_tasks: BackgroundTasks):
    logger.debug(f"[GSV v2] 收到请求：method={request.method}, path={request.url.path}")

    raw = await _read_request_data(request)
    logger.debug(f"[GSV v2] 解析请求数据：{raw}")

    try:
        data = _normalize_webapi_v2_params(raw)
        logger.debug(
            f"[GSV v2] 标准化参数：text={data.get('text', '')[:50]}..., text_lang={data.get('text_lang')}, ref_audio_path={data.get('ref_audio_path')}"
        )
    except HTTPException as e:
        logger.error(f"[GSV v2] 参数标准化失败：status={e.status_code}, detail={e.detail}")
        raise
    except Exception as e:
        logger.error(f"[GSV v2] 参数标准化异常：{type(e).__name__}: {e}")
        raise

    # 必要参数（按 AIChat README 的测试链接）:contentReference[oaicite:3]{index=3}
    text = (data.get("text") or "").strip()
    if not text:
        logger.warning("[GSV v2] text 为空")
        raise HTTPException(status_code=400, detail="text cannot be empty")

    # 你的内部实现如果必须要 sample_rate 等，params_parser 里一般会补齐；
    # 这里不强行校验 sample_rate。

    tts_synthesizer = gsv_tts_state_manager.get_tts_synthesizer()  # type: ignore[reportUnknownMemberType]
    if tts_synthesizer is None:
        logger.error("[GSV v2] TTS synthesizer 未初始化")
        raise HTTPException(status_code=500, detail="TTS synthesizer not initialized")

    logger.debug(f"[GSV v2] 开始生成语音：text={text[:50]}...")

    task = tts_synthesizer.params_parser(data)  # type: ignore[reportUnknownMemberType]
    logger.debug(f"[GSV v2] params_parser 完成：task={task}")

    save_path = tts_synthesizer.generate(task, return_type="filepath")  # type: ignore[reportUnknownMemberType]
    if not isinstance(save_path, str):
        logger.error(f"[GSV v2] 生成失败：save_path={save_path}")
        raise HTTPException(status_code=500, detail="Failed to generate audio file")

    logger.debug(f"[GSV v2] 生成成功：save_path={save_path}")

    out_path = Path(save_path)

    # 输出类型：wav / mp3
    audio_type = str(data.get("audio_type") or "wav").lower()
    if audio_type == "mp3":
        mp3_path = out_path.with_suffix(".mp3")
        file_to_mp3(out_path, mp3_path)
        out_path = mp3_path
        media_type = "audio/mpeg"
        filename = "tts.mp3"
    elif audio_type == "wav":
        media_type = "audio/wav"
        filename = "tts.wav"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported audio_type: {audio_type}")

    # 请求方可能会传 streaming_mode=True（README 里 ffplay 测试就用过）:contentReference[oaicite:4]{index=4}
    streaming_mode = str(data.get("streaming_mode")).lower() in ("1", "true", "yes", "y", "on")

    # （可选）响应结束后清理文件：看你是否想保留生成结果
    # background_tasks.add_task(out_path.unlink, missing_ok=True)

    if streaming_mode:
        return StreamingResponse(
            _iter_file(out_path),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        return FileResponse(out_path, media_type=media_type, filename=filename)
