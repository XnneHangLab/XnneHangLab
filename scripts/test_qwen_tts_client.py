from __future__ import annotations

import argparse
import base64
import io
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, cast

import httpx
import numpy as np
import soundfile as sf
from loguru import logger
from numpy.typing import NDArray

Float32Array = NDArray[np.float32]


def _build_client() -> httpx.Client:
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""

    return httpx.Client(
        trust_env=False,
        transport=httpx.HTTPTransport(local_address="0.0.0.0"),
        follow_redirects=True,
        timeout=120.0,
    )


def _normalize_router_base(server_url: str) -> str:
    base = server_url.rstrip("/")
    if base.endswith("/tts/qwen-tts"):
        return base
    return f"{base}/tts/qwen-tts"


def _as_float32_mono_array(value: Any) -> Float32Array:
    arr = np.asarray(value, dtype=np.float32).squeeze()
    if arr.ndim > 1:
        arr = arr.mean(axis=1, dtype=np.float32)
    return cast("Float32Array", arr)


def _decode_wav_b64_to_pcm(audio_b64: str) -> tuple[Float32Array, int]:
    wav_bytes = base64.b64decode(audio_b64)
    audio_raw, sr_raw = sf.read(  # type: ignore[reportUnknownMemberType]
        io.BytesIO(wav_bytes),
        dtype="float32",
        always_2d=False,
    )
    audio = _as_float32_mono_array(audio_raw)
    return audio, int(sr_raw)


def _iter_sse_events(response: httpx.Response) -> tuple[str, ...] | list[str]:
    """
    简单 SSE 解析器：
    每个事件以空行分隔，只取 data: 开头的行并拼起来。
    """
    events: list[str] = []
    data_lines: list[str] = []

    for line in response.iter_lines():
        if line == "":
            if data_lines:
                events.append("\n".join(data_lines))
                data_lines.clear()
            continue

        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        events.append("\n".join(data_lines))

    return events


def test_health(base_server_url: str) -> None:
    start = time.perf_counter()
    health_base = _normalize_router_base(base_server_url)

    with _build_client() as client:
        response = client.get(f"{health_base}/health")
        response.raise_for_status()
        logger.info(f"health: {response.status_code} {response.json()}")

    elapsed = time.perf_counter() - start
    logger.info(f"health elapsed: {elapsed:.3f}s")


def test_non_stream(
    client: httpx.Client,
    server_base: str,
    out_file: Path,
    text: str,
    *,
    ref_audio: str = "",
    ref_text: str = "",
) -> None:
    start = time.perf_counter()

    data: dict[str, Any] = {
        "text": text,
    }
    files: dict[str, tuple[str, bytes, str]] | None = None

    if ref_text:
        data["ref_text"] = ref_text

    if ref_audio:
        files = {
            "ref_audio": (Path(ref_audio).name, Path(ref_audio).read_bytes(), "audio/wav"),
        }

    response = client.post(
        f"{server_base}/generate",
        data=data,
        files=files,
    )
    response.raise_for_status()

    out_file.write_bytes(response.content)

    elapsed = time.perf_counter() - start
    logger.info(f"non-stream saved => {out_file}")
    logger.info(f"non-stream elapsed: {elapsed:.3f}s")


def test_stream_save(
    client: httpx.Client,
    server_base: str,
    out_file: Path,
    text: str,
    *,
    ref_audio: str = "",
    ref_text: str = "",
) -> None:
    start = time.perf_counter()

    data: dict[str, Any] = {
        "text": text,
    }
    files: dict[str, tuple[str, bytes, str]] | None = None

    if ref_text:
        data["ref_text"] = ref_text

    if ref_audio:
        files = {
            "ref_audio": (Path(ref_audio).name, Path(ref_audio).read_bytes(), "audio/wav"),
        }

    pcm_parts: list[Float32Array] = []
    final_sr: int | None = None
    last_metrics: dict[str, Any] | None = None

    with client.stream(
        "POST",
        f"{server_base}/generate/stream",
        data=data,
        files=files,
        headers={"Accept": "text/event-stream"},
    ) as response:
        response.raise_for_status()

        for event_data in _iter_sse_events(response):
            payload = cast("dict[str, Any]", json.loads(event_data))
            event_type = payload.get("type")

            if event_type == "chunk":
                audio_b64 = cast("str", payload["audio_b64"])
                audio, sr = _decode_wav_b64_to_pcm(audio_b64)

                if final_sr is None:
                    final_sr = sr
                elif final_sr != sr:
                    raise RuntimeError(f"sample rate mismatch: {final_sr} != {sr}")

                if audio.size > 0:
                    pcm_parts.append(audio)

                logger.info(
                    "chunk sr={} ttfa_ms={} rtf={} total_audio_s={} elapsed_ms={}",
                    sr,
                    payload.get("ttfa_ms"),
                    payload.get("rtf"),
                    payload.get("total_audio_s"),
                    payload.get("elapsed_ms"),
                )

            elif event_type == "done":
                last_metrics = payload
                logger.info(f"stream done => {payload}")

            elif event_type == "error":
                raise RuntimeError(f"stream error: {payload.get('message')}")

    if not pcm_parts:
        raise RuntimeError("stream produced no audio chunks")

    merged = np.concatenate(pcm_parts)
    sf.write(out_file, merged, final_sr or 24000, format="WAV", subtype="PCM_16")  # type: ignore[reportUnknownMemberType]

    elapsed = time.perf_counter() - start
    logger.info(f"stream-save saved => {out_file}")
    logger.info(f"stream-save elapsed: {elapsed:.3f}s")
    if last_metrics:
        logger.info(f"final metrics => {last_metrics}")


def test_stream_play_and_save(
    client: httpx.Client,
    server_base: str,
    out_file: Path,
    text: str,
    *,
    ref_audio: str = "",
    ref_text: str = "",
) -> None:
    """
    流式接收：边解码边播放（ffplay raw f32le），同时缓存 PCM，结束后统一写 WAV。
    """
    start = time.perf_counter()

    data: dict[str, Any] = {
        "text": text,
    }
    files: dict[str, tuple[str, bytes, str]] | None = None

    if ref_text:
        data["ref_text"] = ref_text

    if ref_audio:
        files = {
            "ref_audio": (Path(ref_audio).name, Path(ref_audio).read_bytes(), "audio/wav"),
        }

    pcm_parts: list[Float32Array] = []
    final_sr: int | None = None
    play_proc: subprocess.Popen[bytes] | None = None
    last_metrics: dict[str, Any] | None = None

    try:
        with client.stream(
            "POST",
            f"{server_base}/generate/stream",
            data=data,
            files=files,
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()

            for event_data in _iter_sse_events(response):
                payload = cast("dict[str, Any]", json.loads(event_data))
                event_type = payload.get("type")

                if event_type == "chunk":
                    audio_b64 = cast("str", payload["audio_b64"])
                    audio, sr = _decode_wav_b64_to_pcm(audio_b64)

                    if final_sr is None:
                        final_sr = sr
                        ffplay_cmd = [
                            "ffplay",
                            "-autoexit",
                            "-nodisp",
                            "-loglevel",
                            "error",
                            "-f",
                            "f32le",
                            "-ar",
                            str(final_sr),
                            "-ac",
                            "1",
                            "-i",
                            "pipe:0",
                        ]
                        try:
                            play_proc = subprocess.Popen(ffplay_cmd, stdin=subprocess.PIPE)
                        except FileNotFoundError:
                            logger.warning("ffplay not found, stream-play will save only")

                    elif final_sr != sr:
                        raise RuntimeError(f"sample rate mismatch: {final_sr} != {sr}")

                    if audio.size > 0:
                        pcm_parts.append(audio)

                        if play_proc is not None and play_proc.stdin is not None:
                            try:
                                play_proc.stdin.write(audio.astype(np.float32).tobytes())
                                play_proc.stdin.flush()
                            except BrokenPipeError:
                                play_proc = None

                    logger.info(
                        "chunk sr={} ttfa_ms={} rtf={} total_audio_s={} elapsed_ms={}",
                        sr,
                        payload.get("ttfa_ms"),
                        payload.get("rtf"),
                        payload.get("total_audio_s"),
                        payload.get("elapsed_ms"),
                    )

                elif event_type == "done":
                    last_metrics = payload
                    logger.info(f"stream done => {payload}")

                elif event_type == "error":
                    raise RuntimeError(f"stream error: {payload.get('message')}")

    finally:
        if play_proc is not None and play_proc.stdin is not None:
            play_proc.stdin.close()
        if play_proc is not None:
            try:
                play_proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                play_proc.kill()

    if not pcm_parts:
        raise RuntimeError("stream produced no audio chunks")

    merged = np.concatenate(pcm_parts)
    sf.write(out_file, merged, final_sr or 24000, format="WAV", subtype="PCM_16")  # type: ignore[reportUnknownMemberType]

    elapsed = time.perf_counter() - start
    logger.info(f"stream-play-save saved => {out_file}")
    logger.info(f"stream-play-save elapsed: {elapsed:.3f}s")
    if last_metrics:
        logger.info(f"final metrics => {last_metrics}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test qwen-tts SSE server")
    parser.add_argument("--server", default="http://localhost:12393")
    parser.add_argument("--output-dir", default="./tmp/tts_tests")
    parser.add_argument("--ref-audio", default="")
    parser.add_argument("--ref-text", default="")
    parser.add_argument("--text", default="你好，这是一个 qwen tts 的测试。Hello from XnneHangLab.")
    parser.add_argument("--mode", default="all", choices=["all", "health", "non-stream", "stream", "stream-play"])
    return parser.parse_args()


def main() -> None:
    total_start = time.perf_counter()
    args = parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    test_health(args.server)
    if args.mode == "health":
        total_elapsed = time.perf_counter() - total_start
        logger.info(f"total elapsed: {total_elapsed:.3f}s")
        return

    server_base = _normalize_router_base(args.server)

    with _build_client() as client:
        if args.mode in {"all", "non-stream"}:
            test_non_stream(
                client,
                server_base,
                out_dir / "non_stream.wav",
                args.text,
                ref_audio=args.ref_audio,
                ref_text=args.ref_text,
            )

        if args.mode in {"all", "stream"}:
            test_stream_save(
                client,
                server_base,
                out_dir / "stream_save.wav",
                args.text,
                ref_audio=args.ref_audio,
                ref_text=args.ref_text,
            )

        if args.mode in {"all", "stream-play"}:
            test_stream_play_and_save(
                client,
                server_base,
                out_dir / "stream_play_save.wav",
                args.text,
                ref_audio=args.ref_audio,
                ref_text=args.ref_text,
            )

    total_elapsed = time.perf_counter() - total_start
    logger.info(f"total elapsed: {total_elapsed:.3f}s")


if __name__ == "__main__":
    main()
