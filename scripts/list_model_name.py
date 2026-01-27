from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file


def fetch_model_list(base_url: str, api_key: str|None = None, timeout: float = 10.0) -> list[str]:
    """
    Assumes base_url is already a correct OpenAI-compatible prefix, e.g.:
      https://api.openai.com/v1
      https://generativelanguage.googleapis.com/v1beta/openai/
    It will call: GET {base_url.rstrip('/')}/models

    Returns: sorted unique model ids.
    """
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    r = requests.get(url, headers=headers, timeout=timeout)
    if not (200 <= r.status_code < 300):
        # Many providers return HTML when blocked by Cloudflare; keep it short.
        snippet = r.text[:300].replace("\n", " ")
        raise RuntimeError(f"HTTP {r.status_code} from {url}: {snippet}")

    payload: Any = r.json()

    # OpenAI-compatible: {"object":"list","data":[{"id":"..."}]}
    data = payload.get("data") if isinstance(payload, dict) else None  # type: ignore
    if not isinstance(data, list):
        raise RuntimeError(
            f"Unexpected response shape from {url}: top-level keys={list(payload.keys()) if isinstance(payload, dict) else type(payload)}"  # type: ignore
        )  # type: ignore

    ids: list[str] = []
    for item in data:  # type: ignore
        if isinstance(item, dict):
            mid = item.get("id")  # type: ignore
            if isinstance(mid, str):
                ids.append(mid)

    return sorted(set(ids))


def main() -> None:
    """列出配置项中填写 api_key 的模型列表"""
    lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)
    s = lab_settings.agent.llm

    providers: dict[str, tuple[str, str]] = {
        "openai": (s.openai.llm_base_url, s.openai.llm_api_key),
        "cerebras": (s.cerebras.llm_base_url, s.cerebras.llm_api_key),
        "gemini": (s.gemini.llm_base_url, s.gemini.llm_api_key),
        "lingyi": (s.lingyi.llm_base_url, s.lingyi.llm_api_key),
        "oaipro": (s.oaipro.llm_base_url, s.oaipro.llm_api_key),
    }

    model_map: dict[str, list[str]] = {}
    errors: dict[str, str] = {}

    for name, (base_url, api_key) in providers.items():
        if not api_key:
            continue
        try:
            model_map[name] = fetch_model_list(base_url, api_key=api_key)
        except Exception as e:
            errors[name] = str(e)

    for k, v in model_map.items():
        logger.info(f"{k}: {v}")
    summary = {k: len(v) for k, v in model_map.items()}
    logger.info(f"model counts: {summary}")
    logger.info("仅获取了有 api_key 的模型列表")

    # 需要完整列表就写到文件（或直接 print(model_map)）
    with Path("model_list.json").open("w", encoding="utf-8") as f:
        json.dump(model_map, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
