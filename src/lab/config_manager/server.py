from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class ToolPromptsSettings(BaseModel):
    """工具提示词配置。

    这部分配置会在系统提示词构建阶段被读取，用于指导模型输出
    Live2D 表情标签或（可选）思考标签。
    """

    live2d_expression_prompt: Annotated[
        str,
        Field(
            "live2d_expression_prompt",
            title="Live2D 表情提示词",
            description="追加到系统提示词末尾，用于引导模型输出 live2d 表情关键字",
        ),
    ]
    think_tag_prompt: Annotated[
        str | None,
        Field(
            None,
            title="思考标签提示词",
            description="可选，用于引导模型输出括号内心活动，不参与语音合成",
        ),
    ]


class ServerSettings(BaseModel):
    """服务端运行配置。

    负责定义 Web 服务监听地址、端口、角色替代配置目录以及工具提示词。
    """

    conf_version: Annotated[str, Field("v1.1.1", title="配置版本")]
    host: Annotated[str, Field("localhost", title="监听地址")]
    port: Annotated[int, Field(12393, ge=1, le=65535, title="监听端口")]
    config_alts_dir: Annotated[str, Field("characters", title="角色替代配置目录")]
    tool_prompts: Annotated[ToolPromptsSettings, Field(ToolPromptsSettings())]  # pyright: ignore[reportCallIssue]
