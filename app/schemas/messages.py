from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MessageCreate(BaseModel):
    sender_id: str
    receiver_id: str
    student_id: str
    content: str

class MessageResponse(BaseModel):
    id: str
    sender_id: str
    receiver_id: str
    student_id: str
    content: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
