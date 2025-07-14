from __future__ import annotations

import base64
import math
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

# import requests
from fastmcp import FastMCP
from PIL import Image, ImageGrab

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


mcp = FastMCP("vision", lifespan=app_lifespan)


@mcp.tool(name="screen_shot")
def screen_shot() -> str:
    """
    截取用户当前电脑屏幕作为图片来查看用户活动。触发场景示例：
    - "看看我现在的屏幕"
    - "截个图给我看下"
    - "我现在的桌面是什么样子？"
    - "帮我看看屏幕内容"
    - "截图当前窗口"
    - 猜猜我现在在做什么?
    - 猜猜我正在写什么？
    - 猜猜我现在写到哪里了？
    - 你能看到我的屏幕吗？
    - 你看，这是你的源代码。
    - 你能看到你自己吗？
    返回base64编码的JPEG图片。
    """
    # 1. 截取屏幕
    screenshot = ImageGrab.grab()
    # 2. 转换为RGB (JPG不支持透明度)
    if screenshot.mode in ("RGBA", "LA"):
        screenshot = screenshot.convert("RGB")

    # 3. 计算缩放比例
    original_width, original_height = screenshot.size
    scaling_factor = min(1280 / max(original_width, original_height), 1)

    # 4. 执行等比缩放 (如果需要)
    if scaling_factor < 1:
        new_size = (math.ceil(original_width * scaling_factor), math.ceil(original_height * scaling_factor))
        screenshot = screenshot.resize(new_size, Image.LANCZOS)  # type: ignore
        did_resize = True
    else:
        did_resize = False

    # 5. 保存为JPG
    if not Path("./cache").exists():
        Path("./cache").mkdir(exist_ok=True, parents=True)
    screenshot.save("./cache/screenshot.jpg", "JPEG", quality=85)

    # 6. 读取文件并编码为base64
    print(
        f"截图已保存: ./cache/screenshot.jpg | 尺寸: {screenshot.size} | "
        f"质量: {85} | {'已缩放' if did_resize else '原始尺寸'}"
    )

    # return screenshot, did_resize
    with Path("./cache/screenshot.jpg").open("rb") as f:
        img_str = base64.b64encode(f.read()).decode("utf-8")

    return img_str


# 大模型一般自己支持 image url 不必多次一举, 而且 request 容易被当人机拦下来，实在是不好使。
# @mcp.tool()
# def read_image_from_url(url: str) -> str:
#     """
#     当用户提供图片URL时使用此工具获取图像并转换为base64编码。关键词：看到/查看/显示/图片/图像/url

#     """
#     image_url = url
#     response = requests.get(image_url)
#     image_b64 = base64.b64encode(response.content).decode("utf-8")

#     return image_b64


@mcp.prompt("describe_image")
def describe_image() -> str:
    """简短但有细节地描述图片内容"""
    return """
    先看清楚用户问什么，正面回答用户问题，比如能不能看到？先回答能看到或者不能，然后再回答你看到的内容（图片内容）。
    如果用户不是问你图片具体内容或者具体是什么，那你可以选择性少回答一些。
    而对于图片内容你可以这么回答。
    1. 第一句概括主要场景
    2. 第二句补充关键细节
    3. 如果图片中有文字或特殊物体，可以额外提及特别是代码，可以区分它是 Python, 还是 txt 什么的，并且可以读出来一部分你感兴趣的。
    4. 语言自然，避免机械式描述
    """


def run_mcp():
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    mcp.run(
        transport=lab_settings.mcp.vision.transport,
        host=lab_settings.mcp.vision.host,
        port=lab_settings.mcp.vision.port,
        path=lab_settings.mcp.vision.path,
        log_level=lab_settings.mcp.vision.log_level,
    )


if __name__ == "__main__":
    run_mcp()
