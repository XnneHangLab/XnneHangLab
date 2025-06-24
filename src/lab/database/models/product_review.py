from __future__ import annotations

from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field


class ProductReview(BaseModel):
    id: str | None = None  # This is optional for the Pydantic model, but will be set by Beanie
    name: str
    product: str
    rating: float
    review: str
    date: datetime = datetime.now()


class ProductReviewDocument(Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId)  # type: ignore
    name: str
    product: str
    rating: float
    review: str
    date: datetime = datetime.now()

    class Settings:
        name = "product_review"

    class Config:  # type: ignore
        json_schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4a2f",
                "name": "Abdulazeez",
                "product": "TestDriven TDD Course",
                "rating": 4.9,
                "review": "Excellent course!",
                "date": datetime.now(),
            }
        }


class UpdateProductReview(BaseModel):
    # _id 不可以更新，因为它是唯一标识符
    name: str | None = None
    product: str | None = None
    rating: float | None = None
    review: str | None = None
    date: datetime | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Abdulazeez Abdulazeez",
                "product": "TestDriven TDD Course",
                "rating": 5.0,
                "review": "Excellent course!",
                "date": datetime.now(),
            }
        }
