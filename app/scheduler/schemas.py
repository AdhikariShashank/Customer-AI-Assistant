
from pydantic import BaseModel, Field


class ExpirationResult(BaseModel):
    """Summary of an approval expiration run."""

    processed_count: int = Field(default=0, ge=0)
    expired_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
