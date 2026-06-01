from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

class ResultEntry(BaseModel):
    student_id: UUID
    subject_id: UUID
    class_id: UUID
    exam_type: str = Field(..., pattern="^(CAT|EXAM)$", example="CAT")
    score: float = Field(..., ge=0, le=100, example=78.5)
    remarks: str = Field("", example="Shows improvement in algebra.")

class BulkResultRequest(BaseModel):
    teacher_id: UUID = Field(..., description="Teacher submitting the results")
    term: str = Field(..., example="Term 1 2025")
    academic_year: str = Field(..., example="2025")
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