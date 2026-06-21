from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

class ResultEntry(BaseModel):
    student_id: UUID
    subject_id: UUID
    class_id: UUID
    exam_type: str = Field(..., pattern="^(CAT|EXAM)$", example="CAT")
    score: float = Field(..., ge=0, le=100, example=78.5)
    remarks: str = Field("", max_length=200, example="Shows improvement in algebra.")

class BulkResultRequest(BaseModel):
    teacher_id: UUID = Field(..., description="Teacher submitting the results")
    term: str = Field(..., min_length=5, max_length=20, pattern=r"^Term [1-3] 20[2-9][0-9]$", example="Term 1 2025")
    academic_year: str = Field(..., pattern=r"^20[2-9][0-9]$", example="2025")
    results: List[ResultEntry] = Field(..., example=[
        {
            "student_id": "uuid-of-student",
            "subject_id": "uuid-of-mathematics",
            "class_id": "uuid-of-grade-1-orange",
            "exam_type": "CAT",
            "score": 78.5,
            "remarks": "Good effort."
        }
    ])