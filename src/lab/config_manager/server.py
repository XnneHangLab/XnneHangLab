from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class ServerSettings(BaseModel):
    """服务端运行配置。

    负责定义 Web 服务监听地址、端口、角色替代配置目录以及工具提示词。
    """

    host: Annotated[str, Field("localhost", title="监听地址")]
    port: Annotated[int, Field(12393, ge=1, le=65535, title="监听端口")]
    config_alts_dir: Annotated[str, Field("characters", title="角色替代配置目录")]
    uvicorn_log_level: Annotated[str, Field("info", title="Uvicorn 日志等级")]
