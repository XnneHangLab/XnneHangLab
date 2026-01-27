from __future__ import annotations

import json
from pathlib import Path

import requests
from loguru import logger
from pydantic import BaseModel, ValidationError

from lab.config_manager import RootAbsDir, XnneHangLabSettings, load_settings_file


class ModelItem(BaseModel):
    id: str  # 只关心 id，其它字段自动忽略


class ModelsResponse(BaseModel):
    data: list[ModelItem]


def fetch_model_list(base_url: str, api_key: str | None = None, timeout: float = 10.0) -> list[str]:
    url = f"{base_url.rstrip('/')}/models"
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    r = requests.get(url, headers=headers, timeout=timeout)
    try:
        r.raise_for_status()
    except requests.HTTPError as exc:
        # Many providers return HTML when blocked by Cloudflare; keep it short.
        snippet = r.text[:300].replace("\n", " ")
        raise RuntimeError(f"HTTP {r.status_code} from {url}: {snippet}") from exc

    try:
        parsed = ModelsResponse.model_validate(r.json())
    except ValidationError as e:
        raise RuntimeError(f"Invalid /models response from {url}: {e}") from e

    return sorted({m.id for m in parsed.data})


def main() -> None:
    """logger 列出配置项中填写 api_key 的模型列表,并写入 model_list.json
    Returns:
        None. Logs the results and writes them to model_list.json
    """
    lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)
    root_setting: RootAbsDir = lab_settings.root
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
        except requests.exceptions.RequestException as e:
            logger.exception(f"Request error while fetching models for provider '{name}'")
            errors[name] = f"Request failed ({type(e).__name__}): {e}"
        except json.JSONDecodeError as e:
            logger.exception(f"JSON decode error while fetching models for provider '{name}'")
            errors[name] = f"JSON decode failed ({type(e).__name__}): {e}"
        except RuntimeError as e:
            logger.exception(f"Runtime error while fetching models for provider '{name}'")
            errors[name] = f"Runtime error ({type(e).__name__}): {e}"
        except Exception as e:
            logger.exception(f"Unexpected error while fetching models for provider '{name}'")
            errors[name] = f"Unexpected error ({type(e).__name__}): {e}"

    for k, v in model_map.items():
        logger.info(f"{k}: {v}")
    summary = {k: len(v) for k, v in model_map.items()}
    logger.info(f"model counts: {summary}")
    logger.info("仅获取了有 api_key 的模型列表")

    if errors:
        logger.warning(f"failed: {list(errors.keys())}")
        logger.warning("api_key 不正确可能会导致获取模型列表失败")

    # 需要完整列表就写到文件（或直接 print(model_map)）
    with (Path(root_setting.root_dir) / "model_list.json").open("w", encoding="utf-8") as f:
        json.dump(model_map, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
