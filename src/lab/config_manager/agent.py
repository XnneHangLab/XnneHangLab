"""运行 Streamlit 应用前将当前项目的根目录绝对路径写入配置文件
因为 Streamlit 应用启动后，读取根目录绝对路径会默认变成 `.`, 无法访问 `packages`, 而 packages 存储了各自模块的 ui, 必须访问。
所以这里将根目录绝对路径写入配置文件 `root.toml` 中。在 Streamlit 启动前运行，然后供它全局使用。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from lab.config_manager.config import load_settings_file, search_for_settings_file


class AgentSettings(BaseModel):
    openai_base_url: Annotated[str, Field("", title="OpenAI API Base URL")]
    openai_api_key: Annotated[str, Field("", title="OpenAI API Key")]
    openai_model: Annotated[str, Field("", title="OpenAI Model Name")]
    faster_first_response: Annotated[bool, Field(True, title="Enable Faster First Response")]
    segment_method: Literal["regex", "pysbd"] = Field(
        "pysbd",
        title="Segment Method",
        description="Method for segmenting text. 'regex' uses regex, 'pysbd' uses pysbd.",
    )
    interrupt_method: Literal["system", "user"] = Field(
        "user",
        title="Interrupt Method",
        description="Method for writing interruptions signal in chat history. 'system' uses system prompt, 'user' uses user input.",
    )


def main():
    config_path = search_for_settings_file("agent.toml")
    if config_path is not None and config_path.exists():
        config_path.unlink()
    load_settings_file("agent.toml", AgentSettings)
