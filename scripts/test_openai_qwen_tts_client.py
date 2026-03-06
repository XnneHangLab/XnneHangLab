from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from loguru import logger
from openai import OpenAI


def _build_client(base_url: str) -> OpenAI:
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""

    http_client = httpx.Client(
        transport=httpx.HTTPTransport(local_address="0.0.0.0"),
        follow_redirects=True,
        timeout=120.0,
    )
    return OpenAI(api_key="not-needed", base_url=base_url, http_client=http_client)


def _normalize_router_base(server_url: str) -> str:
    base = server_url.rstrip("/")
    if base.endswith("/tts/qwen-tts"):
        return base
    return f"{base}/tts/qwen-tts"


def test_health(base_server_url: str) -> None:
    health_base = _normalize_router_base(base_server_url)
    with httpx.Client(trust_env=False, timeout=10.0) as client:
        response = client.get(f"{health_base}/health")
        response.raise_for_status()
        logger.info(f"health: {response.status_code} {response.json()}")


def test_non_stream(
    client: OpenAI, out_file: Path, text: str, *, extra_body: dict[str, str | bool] | None = None
) -> None:
    response = client.audio.speech.create(
        model="tts-1",
        input=text,
        voice="default",
        response_format="wav",
        extra_body=extra_body,
    )
    response.stream_to_file(str(out_file))
    logger.info(f"non-stream saved => {out_file}")


def test_stream_save(
    client: OpenAI, out_file: Path, text: str, *, extra_body: dict[str, str | bool] | None = None
) -> None:
    with client.audio.speech.with_streaming_response.create(
        model="tts-1",
        input=text,
        voice="default",
        response_format="wav",
        extra_body=extra_body,
    ) as response:
        response.stream_to_file(str(out_file))
    logger.info(f"stream-save saved => {out_file}")


def test_stream_play_and_save(
    client: OpenAI, out_file: Path, text: str, *, extra_body: dict[str, str | bool] | None = None
) -> None:
    """边流式接收边播放（依赖 ffplay），并落盘完整文件。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fifo_path = Path(tmp_dir) / "tts_stream.wav"
        if fifo_path.exists():
            fifo_path.unlink()
        os.mkfifo(fifo_path)

        ffplay_cmd = [
            "ffplay",
            "-autoexit",
            "-nodisp",
            "-loglevel",
            "error",
            str(fifo_path),
        ]
        proc = subprocess.Popen(ffplay_cmd)

        try:
            with (
                client.audio.speech.with_streaming_response.create(
                    model="tts-1",
                    input=text,
                    voice="default",
                    response_format="wav",
                    extra_body=extra_body,
                ) as response,
                fifo_path.open("wb") as fifo_writer,
                out_file.open("wb") as file_writer,
            ):
                for chunk in response.iter_bytes():
                    fifo_writer.write(chunk)
                    fifo_writer.flush()
                    file_writer.write(chunk)
        finally:
            proc.wait(timeout=30)

    logger.info(f"stream-play-save saved => {out_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test qwen-tts OpenAI-compatible server")
    parser.add_argument("--server", default="http://localhost:12393")
    parser.add_argument("--base-url", default="", help="Optional OpenAI base_url override")
    parser.add_argument("--output-dir", default="./tmp/tts_tests")
    parser.add_argument("--ref-audio", default="")
    parser.add_argument("--ref-text", default="")
    parser.add_argument("--text", default="你好，这是一个 qwen tts 的测试。Hello from XnneHangLab.")
    parser.add_argument("--mode", default="all", choices=["all", "health", "non-stream", "stream", "stream-play"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    test_health(args.server)
    if args.mode == "health":
        return

    openai_base = args.base_url.rstrip("/") if args.base_url else ""
    if not openai_base:
        openai_base = f"{_normalize_router_base(args.server)}/v1"

    client = _build_client(openai_base)

    base_text = args.text

    base_extra: dict[str, str | bool] = {}
    if args.ref_audio:
        base_extra["ref_audio"] = args.ref_audio
    if args.ref_text:
        base_extra["ref_text"] = args.ref_text

    non_stream_extra = dict(base_extra)
    non_stream_extra["stream"] = False

    stream_extra = dict(base_extra)
    stream_extra["stream"] = True

    if args.mode in {"all", "non-stream"}:
        test_non_stream(client, out_dir / "non_stream.wav", base_text, extra_body=non_stream_extra)

    if args.mode in {"all", "stream"}:
        test_stream_save(client, out_dir / "stream_save.wav", base_text, extra_body=stream_extra)

    if args.mode in {"all", "stream-play"}:
        try:
            test_stream_play_and_save(client, out_dir / "stream_play_save.wav", base_text, extra_body=stream_extra)
        except FileNotFoundError:
            logger.warning("ffplay not found, skip stream-play test")


if __name__ == "__main__":
    main()
