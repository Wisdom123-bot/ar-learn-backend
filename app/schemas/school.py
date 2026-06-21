from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class ClassCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9 ]+$", example="Grade 1 Orange")
    target_mean_score: Optional[float] = Field(0.0, ge=0, le=100, example=75.5)

class SchoolRegistrationRequest(BaseModel):
    school_name: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9 &'.()/-]+$", example="Moi Educational Centre")
    county: str = Field(..., min_length=3, max_length=50, example="Nairobi")
    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", example="info@moieducational.ac.ke")
    phone: str = Field(..., pattern=r"^(?:\+254|0)[17][0-9]{8}$", example="0712345678")
    number_of_students: int = Field(..., ge=1, le=10000, example=500)
    number_of_teachers: int = Field(..., ge=1, le=500, example=20)
    headteacher_name: Optional[str] = Field(None, min_length=2, max_length=100, pattern=r"^[a-zA-Z .']+$", example="Mr. Otieno")
    dean_name: Optional[str] = Field(None, min_length=2, max_length=100, pattern=r"^[a-zA-Z .']+$", example="Ms. Wanjiku")
    teacher_names: List[str] = Field(..., example=["John Doe", "Jane Smith"])
    classes: List[ClassCreate] = Field(..., example=[{"name": "Grade 1 Orange", "target_mean_score": 75.5}])
    subjects: List[str] = Field(..., example=["Mathematics", "English", "Science"])

class ClassResponse(BaseModel):
    id: UUID
    name: str
    target_mean_score: float
    created_at: datetime
    class Config:
        from_attributes = True

class SubjectResponse(BaseModel):
    id: UUID
    name: str
    class Config:
        from_attributes = True

class TeacherResponse(BaseModel):
    id: UUID
    name: str
    teacher_code: str
    role: str
    created_at: datetime
    class Config:
        from_attributes = True

class SchoolRegistrationResponse(BaseModel):
    message: str = "School registered successfully"
    school_id: UUID
    school_name: str
    county: str
    email: str
    phone: str
    headteacher: Optional[TeacherResponse] = None
    dean: Optional[TeacherResponse] = None
    teachers: List[TeacherResponse] = []
    classes: List[ClassResponse] = []
    subjects: List[SubjectResponse] = []
    class Config:
        from_attributes = True