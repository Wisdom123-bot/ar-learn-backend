from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

class SubjectAssignment(BaseModel):
    class_id: UUID
    subject_id: UUID
    is_class_teacher: bool = Field(False, description="Mark if this teacher is the class teacher for this class")

class TeacherAssignRequest(BaseModel):
    assignments: List[SubjectAssignment] = Field(..., example=[
        {"class_id": "uuid-of-grade-1-orange", "subject_id": "uuid-of-mathematics", "is_class_teacher": True},
        {"class_id": "uuid-of-grade-1-orange", "subject_id": "uuid-of-english", "is_class_teacher": False}
    ])