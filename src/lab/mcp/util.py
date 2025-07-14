from __future__ import annotations

from pathlib import Path
from typing import Any


def read_prompt_from_text_file(system_prompt_name: str) -> str:
    prompt_text_path = Path("prompts") / f"{system_prompt_name}.txt"
    if not prompt_text_path.exists():
        raise ValueError(f"prompt file {prompt_text_path} not exists")
    with prompt_text_path.open("r", encoding="utf-8") as f:
        prompt_text = f.read()
    return prompt_text


# 避免反復地添加 type: ignore, 僅能處理 str 返回。
def read_prompt_from_mcp_prompt_template(response: Any) -> str:
    try:
        return response.messages[0].content.text  # type: ignore
    except Exception as e:
        print(response)
        return f"parse prompt template error: {e}"


def read_result_from_mcp_tool_response(response: Any) -> str:
    try:
        return response.content[0].text  # type: ignore
    except Exception as e:
        print(response)
        return f"parse tool response error: {e}"
