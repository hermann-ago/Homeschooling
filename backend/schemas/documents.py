from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    size_bytes: Optional[int] = None
    page_count: int
    status: str
    created_at: datetime
    sha256: Optional[str] = None
    source: Optional[str] = None


class StorageUsageResponse(BaseModel):
    bytes_used: int
