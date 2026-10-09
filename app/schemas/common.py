from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail