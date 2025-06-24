from __future__ import annotations

from datetime import datetime

from beanie import Document
from pydantic import BaseModel


class ProductReview(BaseModel):
    name: str
    product: str
    rating: float
    review: str
    date: datetime = datetime.now()


class ProductReviewDocument(Document):
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
                "name": "Abdulazeez",
                "product": "TestDriven TDD Course",
                "rating": 4.9,
                "review": "Excellent course!",
                "date": datetime.now(),
            }
        }


class UpdateProductReview(BaseModel):
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
