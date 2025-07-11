# copyright@https://github.com/yutto-dev/yutto
from __future__ import annotations

import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from mcp.server.session import ServerSession
    from mcp.shared.context import RequestContext


@dataclass
class AppContext:
    date_time: str = datetime.now().isoformat()


@asynccontextmanager
async def app_lifespan(server: FastMCP[AppContext]) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with type-safe context"""
    # Initialize on startup
    try:
        yield AppContext(date_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    finally:
        # Cleanup on shutdown
        pass


mcp = FastMCP("timeemi", lifespan=app_lifespan)


@mcp.tool()
async def get_date_and_time(
    ctx: Context,
) -> str:
    """
    Use this tool to get current date time with format YYYY-MM-DD HH:MM:SS.

    """
    # the docs string will be the description for tool.
    request_context: RequestContext[ServerSession, AppContext, Any] = ctx.request_context  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    # download_manager: DownloadManager = request_context.lifespan_context.download_manager
    # await download_manager.add_task(DownloadTask(args=parse_args(url, dir)))
    # 转换为 DDDD-MM-DD HH:MM:SS
    request_context.lifespan_context.date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return request_context.lifespan_context.date_time


@mcp.prompt("convert_time_readable")
def convert_isoformat_time_to_tts_text(time_str: str) -> str:
    """Convert ISO timestamp to spoken format based on response language."""
    return f"""
            如果回复是中文，请参照此转换规则：
            (2004-10-14 12:21:41 → 二零零四年十月十四日，十二时二十一分四十一秒)
            将以下时间转换为中文读音格式：\n{time_str}

            If the response is in English, follow this format:
            (2004-10-14 12:21:41 → October 14, 2004, twelve twenty-one forty-one)
            Convert the time to English spoken format：\n{time_str}

            もし返信が日本語の場合、この形式に従ってください：
            (2004-10-14 12:21:41 → 2004年10月14日、12時21分41秒)
            以下の時間を日本語の読み方に変換してください：\n{time_str},
            
            只需要返回和用户语言相同的格式即可,
            当用户问你几点时，你只需要回答十二时二十一分，不需要回答秒,
            当用户问你今天是几号时，你可以选择回答 二零零四年十月十四日 或者 十月十四日。
            """


@mcp.tool
def roll_dice(n_dice: int) -> list[int]:
    """Roll `n_dice` 6-sided dice and return the results."""
    return [random.randint(1, 6) for _ in range(n_dice)]


def run_mcp():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp()
