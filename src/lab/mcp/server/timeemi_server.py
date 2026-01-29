from __future__ import annotations

import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from lab.config_manager import XnneHangLabSettings, load_settings_file

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
    """


@mcp.prompt("limit_time_response")
def limit_time_response(user_input: str) -> str:
    return f"""
    只需要返回和用户语言相同的格式即可,你转换得到的时间是**现在这个时刻的时间**。
    当用户问你几点时，你只需要回答十二时二十一分，不需要回答秒,当然你可以加上上午，下午，晚上,傍晚等修饰语。
    当用户问你今天是几号时，你可以选择回答 二零零四年十月十四日 或者 十月十四日,尽量选择后者，因为比较短。
    你也需要自己应付用户刁钻的回答比如昨天，明天，大后天，一个小时前。甚至问你时区时差问题。
    现在用户问的是:{user_input}
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


class RollDiceByCurrentTimeResult(BaseModel):
    """
    roll_dice_by_current_time 的返回结果。

    示例：
    {
      "unit": "hour",
      "now": "2026-01-28 09:57:19",
      "value": 9,
      "n_dice": 4,
      "numbers": [4, 1, 4, 6]
    }
    """

    unit: Literal["hour", "minute", "second"] = Field(..., description="使用的时间单位")
    now: str = Field(..., description="服务器当前时间，格式 YYYY-MM-DD HH:MM:SS")
    value: int = Field(..., description="从当前时间中提取的数值（hour/minute/second）")
    n_dice: int = Field(..., description="最终掷骰子的数量（>=1）")
    numbers: list[int] = Field(..., description="掷骰结果列表")


@mcp.tool()
def roll_dice_by_current_time(
    unit: Literal["hour", "minute", "second"],
) -> RollDiceByCurrentTimeResult:
    """
    根据当前时间决定掷骰数量，然后返回掷骰结果。

    参数：
    - unit: 使用当前时间的哪个单位来决定掷骰数量  ["hour", "minute", "second"]
    hour: 使用当前小时数决定掷骰数量 (0-23), 几点，几小时。
    minute: 使用当前分钟数决定掷骰数量 (0-59), 几分。
    second: 使用当前秒数决定掷骰数量 (0-59), 几秒。"""
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    if unit == "hour":
        value = now_dt.hour
    elif unit == "minute":
        value = now_dt.minute
    else:
        value = now_dt.second

    if value == 0:
        n_dice = 1
    else:
        n_dice = value

    numbers = [random.randint(1, 6) for _ in range(n_dice)]
    return RollDiceByCurrentTimeResult(unit=unit, now=now_str, value=value, n_dice=n_dice, numbers=numbers)


def run_mcp():
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    mcp.run(
        transport=lab_settings.mcp.servers.timeemi.transport,
        host=lab_settings.mcp.servers.timeemi.host,
        port=lab_settings.mcp.servers.timeemi.port,
        path=lab_settings.mcp.servers.timeemi.path,
        log_level=lab_settings.mcp.servers.timeemi.log_level,
    )


if __name__ == "__main__":
    run_mcp()
