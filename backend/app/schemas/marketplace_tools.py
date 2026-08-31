from __future__ import annotations

from pydantic import BaseModel


JsonScalar = str | int | float | bool | None


class ArtifactLink(BaseModel):
    filename: str
    download_url: str
    media_type: str


class MarketplaceToolResult(BaseModel):
    tool: str
    stats: dict[str, JsonScalar]
    preview: list[dict[str, JsonScalar]]
    artifacts: list[ArtifactLink]
    warnings: list[str]


class PromoCategoryOption(BaseModel):
    category: str
    product_count: int


class PromoCategoriesResponse(BaseModel):
    categories: list[PromoCategoryOption]


class PromoCategoryOverrideInput(BaseModel):
    category: str
    min_discount: float | None = None
    max_discount: float | None = None
    exclude: bool = False
