from __future__ import annotations

import json
from pathlib import Path

# from typing import TYPE_CHECKING
import requests
import streamlit as st
from dotenv import load_dotenv

from lab._session_keys import session_keys

load_dotenv()

sdk_base_url = "https://api.lingyiwanwu.com"
sdk_key = "d3f9935e076142b3afcc47a6a0cab84d"

# --- Configuration ---
# settings = load_settings_file("config.toml", ServiceSettings)
OPENAI_API_KEY = "d3f9935e076142b3afcc47a6a0cab84d"
OPENAI_ENDPOINT = f"{sdk_base_url}/v1/chat/completions"  # Use Chat Completions endpoint
MODEL = "yi-lightning"
SYSTEMPROMOT = Path("./prompts/paimeng.txt").read_text(encoding="utf-8").strip()  # 派蒙的promot

if session_keys["text_response"] not in st.session_state:
    st.session_state[session_keys["text_response"]] = ""  # 初始化会话状态
if session_keys["short_term_memory"] not in st.session_state:
    st.session_state[session_keys["short_term_memory"]] = []  # 初始化短期记忆


def get_openai_response(
    prompt: str,
    model: str = MODEL,
    max_tokens: int = 15000,
    temperature: float = 0.5,
    n: int = 1,
    stop: list[str] | None = None,
    presence_penalty: float = 0,
    frequency_penalty: float = 0,
) -> str:
    """
    获取OpenAI API的响应（同步，非流式）
    """
    # settings: ServiceSettings = load_settings_file("config.toml", ServiceSettings)
    # OPENAI_API_KEY: str = settings.sdk_key
    # OPENAI_ENDPOINT: str = settings.sdk_base_url + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    if len(st.session_state[session_keys["short_term_memory"]]) == 0:
        st.session_state[session_keys["short_term_memory"]].append({"role": "system", "content": SYSTEMPROMOT})
    st.session_state[session_keys["short_term_memory"]].append(
        {"role": "user", "content": prompt}
    )  # 添加用户输入到短期记忆中
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEMPROMOT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "n": n,
        "stop": stop,
        "presence_penalty": presence_penalty,
        "frequency_penalty": frequency_penalty,
        "stream": False,
    }
    response = requests.post(OPENAI_ENDPOINT, headers=headers, data=json.dumps(data))
    response.raise_for_status()
    response_json = response.json()
    st.session_state[session_keys["text_response"]] = response_json["choices"][0]["message"]["content"].strip()
    st.session_state[session_keys["short_term_memory"]].append(
        {"role": "assistant", "content": st.session_state[session_keys["text_response"]]}
    )  # 添加助手响应到短期记忆中
    return response_json["choices"][0]["message"]["content"].strip()
