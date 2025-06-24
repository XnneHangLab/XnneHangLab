from __future__ import annotations

import motor.motor_asyncio
from beanie import init_beanie  # type: ignore

from lab.database.models.product_review import ProductReviewDocument


async def init_db():
    client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017/productreviews")  # type: ignore

    await init_beanie(database=client.db_name, document_models=[ProductReviewDocument])  # type: ignore
