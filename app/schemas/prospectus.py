from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ProspectusResponse(BaseModel):
    id: int
    school_id: str
    file_url: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None  # bytes
    uploaded_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
