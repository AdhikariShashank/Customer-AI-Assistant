from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cart import AddCartItemRequest
from app.schemas.product import ProductSearchParams


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0)


class RemoveItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)


class GetOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(gt=0)