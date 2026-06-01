from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import time


class TimetableEntryCreate(BaseModel):
    class_id: UUID
    subject_id: UUID
    teacher_id: UUID
    day_of_week: str = Field(..., pattern="^(Monday|Tuesday|Wednesday|Thursday|Friday)$")
    start_time: str = Field(..., example="08:00")
    end_time: str = Field(..., example="08:40")


class TimetableEntryResponse(BaseModel):
    id: UUID
    class_id: UUID
    class_name: str
    subject_id: UUID
    subject_name: str
    teacher_id: UUID
    teacher_name: str
    day_of_week: str
    start_time: str
    end_time: str
    created_at: str

    class Config:
        from_attributes = True


class BulkTimetableRequest(BaseModel):
    school_id: UUID
    entries: List[TimetableEntryCreate]