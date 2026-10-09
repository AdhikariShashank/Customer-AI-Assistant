
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    description: str | None = None
    price: Decimal
    stock: int
    metadata: dict | None = Field(
        default=None,
        validation_alias="metadata_json",
    )
    created_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int


class ProductSearchParams(BaseModel):
    query: str | None = None
    category: str | None = None
    max_price: Decimal | None = Field(default=None, gt=0)
    min_price: Decimal | None = Field(default=None, gt=0)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)