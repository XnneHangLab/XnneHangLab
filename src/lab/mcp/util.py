from __future__ import annotations

from typing import Any


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
