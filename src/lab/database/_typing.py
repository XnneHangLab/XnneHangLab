from __future__ import annotations

from typing import TypedDict


class ProductReviewDict(TypedDict):
    _id: str
    name: str
    product: str
    rating: float
    review: str
    date: str  # datetime.now()


class MessageResponse(TypedDict):
    message: str
