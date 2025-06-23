from __future__ import annotations

import motor.motor_asyncio
from beanie import init_beanie

from lab.database.models.product_review import ProductReview


async def init_db():
    client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017/productreviews")

    await init_beanie(database=client.db_name, document_models=[ProductReview])
