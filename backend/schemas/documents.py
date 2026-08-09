from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    size_bytes: int
    page_count: int
    status: str
    created_at: datetime
    blob_path: str


class StorageUsageResponse(BaseModel):
    bytes_used: int
    byte_limit: int = 1_073_741_824
    warning_threshold: float = 0.8
