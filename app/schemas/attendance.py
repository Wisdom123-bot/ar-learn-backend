from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import date


class AttendanceEntry(BaseModel):
    student_id: UUID
    date: date
    status: str = Field(..., pattern="^(Present|Absent|Sick|Suspended)$", example="Present")


class BulkAttendanceRequest(BaseModel):
    class_id: UUID
    recorded_by: Optional[UUID] = None   # teacher who recorded (optional)
    records: List[AttendanceEntry] = Field(..., min_length=1)


class AttendanceStats(BaseModel):
    student_id: UUID
    student_name: str
    total_days: int
    present: int
    absent: int
    sick: int
    suspended: int
    attendance_pct: float