from __future__ import annotations

from typing import List

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException

from lab.database.models.product_review import ProductReview, UpdateProductReview

router = APIRouter()


@router.post("/", response_description="Review added to the database")
async def add_product_review(review: ProductReview) -> dict[str, str]:
    await review.create()
    return {"message": "Review added successfully"}


@router.get("/{id}", response_description="Review record retrieved")
async def get_review_record(id: PydanticObjectId) -> ProductReview:
    review = await ProductReview.get(id)
    return review


@router.get("/", response_description="Review records retrieved")
async def get_reviews() -> List[ProductReview]:
    reviews = await ProductReview.find_all().to_list()
    return reviews


@router.patch("/{id}", response_description="Review record updated")
async def update_student_data(id: PydanticObjectId, req: UpdateProductReview) -> ProductReview:
    # 1. 获取现有记录
    existing_review = await ProductReview.get(id)
    if not existing_review:
        print(f"Review with id {id} not found.")
        raise HTTPException(status_code=404, detail="Review record not found!")

    # 2. 从请求体中获取用户实际提供的非空值。
    # `model_dump(exclude_unset=True)` 是这里的核心！
    # 它会创建一个字典，仅包含那些在原始请求 JSON 中实际被提供过的字段。
    # 那些用户没传的（因为它们是 `Optional`），将不会被包含在 `update_fields` 字典中。
    update_fields = req.model_dump(exclude_unset=True)  # Pydantic v2
    # 如果是 Pydantic v1，请使用 req.dict(exclude_unset=True)

    # 3. 检查是否有任何需要更新的字段。
    # 如果请求体为空，或者所有字段都是 None（并且 exclude_unset=True 过滤掉了它们），
    # 那么 update_fields 将是空的，无需进行数据库操作。
    if not update_fields:
        return existing_review  # 直接返回现有记录，不做任何更新

    # 4. 使用 MongoDB 的 $set 操作符进行局部更新。
    # Beanie 的 update() 方法可以直接接收一个包含 MongoDB 操作符的字典。
    # `$set` 会确保只有 `update_fields` 中包含的字段才会被修改。
    # 其他未在 `update_fields` 中的字段，在数据库中将**保持不变**。
    await existing_review.update({"$set": update_fields})

    # 5. 返回更新后的记录。
    # `existing_review` 对象在内存中通常会被 Beanie 的 `update()` 方法更新，
    # 所以直接返回它通常是可行的。
    # 如果需要确保返回的是数据库中的最新状态（例如，其他异步操作可能同时修改了数据），
    # 可以选择重新从数据库中加载一次：
    # updated_review = await ProductReview.get(id)
    # return updated_review
    return existing_review


@router.put("/{id}", response_description="Review record fully updated")
async def replace_review_data(id: PydanticObjectId, review_data: ProductReview) -> ProductReview:
    """
    通过完全替换现有评论记录来进行全量更新。
    如果请求体中缺少任何必填字段，或者字段类型不匹配，将返回 422 错误。
    """
    # 1. 尝试从数据库中获取现有记录
    existing_review = await ProductReview.get(id)

    # 2. 如果记录不存在，则返回 404 Not Found
    if not existing_review:
        print(f"Review with id {id} not found for PUT request.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review record not found!")

    # 3. 将传入的 ProductReview 对象转换为字典。
    # 这一步会包含所有字段，因为 ProductReview 模型中的字段通常都是必填的。
    # model_dump() 在 Pydantic v2 中使用。
    # 如果是 Pydantic v1，请使用 review_data.dict()
    update_data = review_data.model_dump(by_alias=True)  # by_alias=True 如果你有别名配置

    # 4. 在更新操作之前，移除 _id 字段。
    # MongoDB 在更新时不需要 _id 字段在 $set 内部。
    # Beanie 通常会处理好这个，但显式移除更安全。
    update_data.pop("id", None)  # Pydantic 模型中的 id 字段对应 MongoDB 的 _id

    # 5. 执行替换操作。
    # Beanie 的 save() 方法在文档有 _id 时会执行更新。
    # 但为了确保是“替换”语义，最直接的方式是使用 Beanie 的 replace() 方法
    # 或者，我们也可以通过创建新实例并指定 _id 然后 save()

    # 推荐使用 save()，但要确保传入的 id 绑定到 Beanie 对象的 id 上
    # 创建一个新实例，并强制设置其 _id 为要更新的文档的 _id，然后保存
    new_review = ProductReview(**update_data)
    new_review.id = id  # 确保新的文档实例知道它是对哪个 _id 进行操作

    await new_review.save()  # 这将根据 new_review.id(_id) 执行 replaceOne

    # 6. 返回更新后的记录
    return new_review


@router.delete("/{id}", response_description="Review record deleted from the database")
async def delete_student_data(id: PydanticObjectId) -> dict[str, str]:
    record = await ProductReview.get(id)

    if not record:
        raise HTTPException(status_code=404, detail="Review record not found!")

    await record.delete()
    return {"message": "Record deleted successfully"}
