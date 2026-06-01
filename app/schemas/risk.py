from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID


class StudentRiskProfile(BaseModel):
    student_id: UUID
    student_name: str
    admission_number: str
    class_name: str
    current_mean: Optional[float] = None
    attendance_pct: Optional[float] = None
    risk_flags: List[str] = []