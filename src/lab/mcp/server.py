from __future__ import annotations

import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from fastmcp import FastMCP

if TYPE_CHECKING:
    #     from mcp.server.session import ServerSession
    #     from mcp.shared.context import RequestContext
    from collections.abc import AsyncIterator


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
async def get_date_and_time() -> str:
    """
    Use this tool to get current date time with format YYYY-MM-DD HH:MM:SS.

    """
    # the docs string will be the description for tool.
    # request_context: RequestContext[ServerSession, AppContext, Any] = ctx.request_context  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    # download_manager: DownloadManager = request_context.lifespan_context.download_manager
    # await download_manager.add_task(DownloadTask(args=parse_args(url, dir)))
    # 转换为 DDDD-MM-DD HH:MM:SS
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return date_time


@mcp.prompt("convert_time_readable")
def convert_isoformat_time_to_tts_text(time_str: str) -> str:
    """Convert ISO timestamp to spoken format based on response language."""
    return f"""
    如果回复是中文，请参照此转换规则：
    (2004-10-14 12:21:41 → 二零零四年十月十四日，十二时二十一分四十一秒)
    将以下时间转换为中文读音格式：{time_str}

    If the response is in English, follow this format:
    (2004-10-14 12:21:41 → October 14, 2004, twelve twenty-one forty-one)
    Convert the time to English spoken format：{time_str}

    もし返信が日本語の場合、この形式に従ってください：
    (2004-10-14 12:21:41 → にせんよねん じゅうがつ じゅうよっか じゅうにじ にじゅういっぷん よんじゅういちびょう)
    以下の時間を平仮名で変換してください：{time_str},

    只需要返回和用户语言相同的格式即可,你转换得到的时间是**现在这个时刻的时间**。
    当用户问你几点时，你只需要回答十二时二十一分，不需要回答秒,当然你可以加上上午，下午，晚上,傍晚等修饰语。
    当用户问你今天是几号时，你可以选择回答 二零零四年十月十四日 或者 十月十四日,尽量选择后者，因为比较短。
    你也需要自己应付用户刁钻的回答比如昨天，明天，大后天，一个小时前。甚至问你时区时差问题。
    """


@mcp.tool
def roll_dice(n_dice: int) -> list[int]:
    """Roll `n_dice` 6-sided dice and return the results."""
    return [random.randint(1, 6) for _ in range(n_dice)]


@mcp.prompt("convert_list_int_readable")
def convert_list_int_to_readable_text(numbers: list[int]) -> str:
    """Convert a list of numbers to a readable text."""
    return f"""
    你需要将数字列表转换为用户易读的文字：
    示例输入: [1,2,3,4,5,6]

    转换规则：
    中文 → 一、二、三、四、五、六
    English → One, Two, Three, Four, Five, Six
    日本語 → いち、に、さん、よん、ご、ろく

    当前需要转换的数字列表：{", ".join(map(str, numbers))}
    请根据用户语言返回对应格式
    """


def run_mcp():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp()
