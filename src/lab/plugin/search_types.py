from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class WebSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Search query.")
    max_results: int = Field(5, ge=1, le=10, description="Number of search results to return.")


class WebSearchResultItem(BaseModel):
    title: str
    url: AnyHttpUrl
    snippet: str | None = None


class WebSearchResult(BaseModel):
    query: str
    results: list[WebSearchResultItem]
