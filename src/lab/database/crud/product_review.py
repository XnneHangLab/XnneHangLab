from __future__ import annotations

from typing import TYPE_CHECKING

import requests

from lab.database.models.product_review import ProductReview, UpdateProductReview
from lab.database.typing import MessageResponse, ProductReviewDict
from lab.utils.console.logger import Badge, Logger

# FastAPI 应用程序的基准 URL
# 如果你的 FastAPI 在本地运行，端口可能是 8000
BASE_URL = "http://127.0.0.1:8000"  # 请根据你的实际 FastAPI 运行地址修改

# TODO: 把 dict[str,str] 预先转为 Pydantic 模型然后转为 TypedDict


def add_product_review(
    review_data: ProductReview,
) -> (
    MessageResponse | None
):  # Changed function signature to receive ProductReview object and return ProductReview or None
    """
    Add a new product review (POST /)
    """
    Logger.custom("添加产品评论", badge=Badge("ADD", fore="black", back="cyan"))
    url = f"{BASE_URL}/"
    # Use review_data.model_dump(mode='json') to convert the Pydantic object to a dictionary,
    # ensuring datetime objects are correctly serialized to ISO format strings
    payload = review_data.model_dump(mode="json")
    try:
        response = requests.post(url, json=payload)  # requests library automatically serializes the dictionary to JSON
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        response_json = response.json()  # Get the JSON response
        Logger.info("添加成功")

        # Parse the JSON response back into a ProductReview object
        # This will also handle datetime string parsing if the 'date' field is present and valid
        return MessageResponse(**response_json)  # Use model_validate for parsing from dict
    except requests.exceptions.RequestException as e:
        Logger.error(f"添加产品评论时发生错误: {e}")
        if hasattr(e, "response") and e.response is not None:
            Logger.error(f"错误响应: {e.response.text}")
        return None
    except Exception as e:  # Catch Pydantic validation errors or other parsing issues
        Logger.error(f"解析服务器响应时发生错误: {e}")
        return None


def get_all_reviews() -> list[ProductReviewDict] | None:
    """
    Get all product reviews (GET /)
    """
    Logger.custom("获取所有产品评论", badge=Badge("LIST", fore="black", back="cyan"))
    url = f"{BASE_URL}/"
    try:
        response = requests.get(url)
        response.raise_for_status()
        reviews_json = response.json()
        Logger.info("所有评论:")

        parsed_reviews: list[ProductReviewDict] = []
        for review_data in reviews_json:
            # Validate each item in the list
            if TYPE_CHECKING:
                _ = ProductReviewDict(**review_data)  # Type check

            # Parse into Pydantic model first, then to dict for TypedDict return type
            parsed_review = ProductReview.model_validate(review_data)
            parsed_reviews.append(ProductReviewDict(**parsed_review.model_dump(mode="json")))

        for review in parsed_reviews:
            print(review)
        return parsed_reviews
    except requests.exceptions.RequestException as e:
        Logger.error(f"获取所有评论时发生错误: {e}")
        if hasattr(e, "response") and e.response is not None:
            Logger.error(f"错误响应: {e.response.text}")
        return None
    except Exception as e:
        Logger.error(f"解析所有评论时发生错误: {e}")
        return None


def get_review_by_id(review_id: str) -> ProductReviewDict | None:
    """
    Get a single product review by ID (GET /{id})
    """
    Logger.custom("根据 ID 获取产品评论", badge=Badge("GET", fore="black", back="cyan"))
    url = f"{BASE_URL}/{review_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        review_json = response.json()

        # Validate the response JSON against ProductReviewDict
        if TYPE_CHECKING:
            _ = ProductReviewDict(**review_json)  # Type check

        # Parse into Pydantic model, then to dict for TypedDict return type
        parsed_review = ProductReview.model_validate(review_json)
        result_dict = parsed_review.model_dump(mode="json")
        Logger.info(f"ID 为 '{review_id}' 的评论: {result_dict}")
        return ProductReviewDict(**result_dict)
    except requests.exceptions.RequestException as e:
        Logger.error(f"根据 ID '{review_id}' 获取评论时发生错误: {e}")
        if hasattr(e, "response") and e.response is not None:
            Logger.error(f"错误响应: {e.response.text}")
        return None
    except Exception as e:
        Logger.error(f"解析 ID 为 '{review_id}' 的评论时发生错误: {e}")
        return None


def update_product_review_partial(review_id: str, updates: UpdateProductReview) -> ProductReviewDict | None:
    """
    Partially update a product review (PATCH /{id})
    The 'updates' object only contains the fields you want to update
    """
    Logger.custom("局部更新产品评论", badge=Badge("UPDATE", fore="black", back="cyan"))
    url = f"{BASE_URL}/{review_id}"
    # Convert UpdateProductReview object to dictionary, excluding unset fields for partial update
    payload = updates.model_dump(mode="json", exclude_unset=True)
    try:
        response = requests.patch(url, json=payload)
        response.raise_for_status()
        updated_review_json = response.json()

        # Validate the response JSON against ProductReviewDict
        if TYPE_CHECKING:
            _ = ProductReviewDict(**updated_review_json)  # Type check

        # Parse into Pydantic model, then to dict for TypedDict return type
        parsed_review = ProductReview.model_validate(updated_review_json)
        result_dict = parsed_review.model_dump(mode="json")
        Logger.info(f"ID 为 '{review_id}' 的评论已更新 (局部): {result_dict}")
        return ProductReviewDict(**result_dict)
    except requests.exceptions.RequestException as e:
        Logger.error(f"更新 ID 为 '{review_id}' 的评论时发生错误 (局部): {e}")
        if hasattr(e, "response") and e.response is not None:
            Logger.error(f"错误响应: {e.response.text}")
        return None
    except Exception as e:
        Logger.error(f"解析局部更新后的评论时发生错误: {e}")
        return None


def replace_product_review_full(review_id: str, new_data: ProductReview) -> ProductReviewDict | None:
    """
    Completely replace a product review (PUT /{id})
    The 'new_data' object must contain all required fields
    """
    Logger.custom("完全替换产品评论", badge=Badge("REPLACE", fore="black", back="cyan"))
    url = f"{BASE_URL}/{review_id}"
    # Convert ProductReview object to dictionary for full replacement
    payload = new_data.model_dump(mode="json", exclude_none=True)  # exclude_none for consistency
    try:
        response = requests.put(url, json=payload)
        response.raise_for_status()
        replaced_review_json = response.json()

        # Validate the response JSON against ProductReviewDict
        if TYPE_CHECKING:
            _ = ProductReviewDict(**replaced_review_json)  # Type check

        # Parse into Pydantic model, then to dict for TypedDict return type
        parsed_review = ProductReview.model_validate(replaced_review_json)
        result_dict = parsed_review.model_dump(mode="json")
        Logger.info(f"ID 为 '{review_id}' 的评论已更新 (完全替换): {result_dict}")
        return ProductReviewDict(**result_dict)
    except requests.exceptions.RequestException as e:
        Logger.error(f"替换 ID 为 '{review_id}' 的评论时发生错误 (完全替换): {e}")
        if hasattr(e, "response") and e.response is not None:
            Logger.error(f"错误响应: {e.response.text}")
        return None
    except Exception as e:
        Logger.error(f"解析完全替换后的评论时发生错误: {e}")
        return None


def delete_product_review(review_id: str) -> MessageResponse | None:  # Return type changed to dict | None
    """
    Delete a product review (DELETE /{id})
    """
    Logger.custom("删除产品评论", badge=Badge("DELETE", fore="black", back="red"))
    url = f"{BASE_URL}/{review_id}"
    try:
        response = requests.delete(url)
        response.raise_for_status()
        Logger.info(f"ID 为 '{review_id}' 的评论已删除")
        return MessageResponse(**response.json())  # Backend returns {"message": "Record deleted successfully"}
    except requests.exceptions.RequestException as e:
        Logger.error(f"删除 ID 为 '{review_id}' 的评论时发生错误: {e}")
        if hasattr(e, "response") and e.response is not None:
            Logger.error(f"错误响应: {e.response.text}")
        return None
    except Exception as e:
        Logger.error(f"删除评论时发生错误: {e}")
        return None
