from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class BadgeBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    category: Optional[str] = "Academic"

class Badge(BadgeBase):
    id: str

    class Config:
        from_attributes = True

class StudentBadgeAward(BaseModel):
    student_id: str
    badge_id: str
    awarded_by: str
    term: str

class StudentBadgeResponse(BaseModel):
    id: str
    student_id: str
    badge: Badge
    awarded_by_name: Optional[str] = None
    awarded_at: datetime
    term: str

    class Config:
        from_attributes = True
