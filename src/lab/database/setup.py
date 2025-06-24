from __future__ import annotations

import motor.motor_asyncio
from beanie import init_beanie  # type: ignore

from lab.database.models.product_review import ProductReviewDocument
from lab.utils.console.logger import Logger


async def init_db():
    client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017/productreviews")  # type: ignore
    Logger.info("等待连接 MongoDB...")
    await init_beanie(database=client.XnneHangLab, document_models=[ProductReviewDocument])  # type: ignore
    Logger.info("MongoDB 连接成功，Beanie 初始化完成。")
