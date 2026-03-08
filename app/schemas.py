from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class LinkCreate(BaseModel):
    original_url: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None


class LinkUpdate(BaseModel):
    original_url: str


class LinkStats(BaseModel):
    original_url: str
    created_at: datetime
    clicks: int
    last_used: Optional[datetime]