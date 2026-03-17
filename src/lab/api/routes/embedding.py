from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from lab.api.logic.embedding import DEFAULT_EMBEDDING_MODEL_NAME, embed

router = APIRouter(tags=["embedding"])


class EmbeddingRequest(BaseModel):
    input: Annotated[str | list[str], Field(..., title="Embedding input")]
    model: Annotated[str, Field(DEFAULT_EMBEDDING_MODEL_NAME, title="Embedding model name")]


class EmbeddingDataItem(BaseModel):
    object: Literal["embedding"] = "embedding"
    embedding: list[float]
    index: int


class EmbeddingUsage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[EmbeddingDataItem]
    model: str
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)


@router.post("/v1/embeddings")
async def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    texts = [request.input] if isinstance(request.input, str) else list(request.input)
    if not texts:
        raise HTTPException(status_code=400, detail="input must not be empty")

    try:
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(None, embed, texts)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding inference failed: {exc}") from exc

    return EmbeddingResponse(
        data=[
            EmbeddingDataItem(
                embedding=vector,
                index=index,
            )
            for index, vector in enumerate(vectors)
        ],
        model=request.model or DEFAULT_EMBEDDING_MODEL_NAME,
    )
