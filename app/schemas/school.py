from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class ClassCreate(BaseModel):
    name: str = Field(..., example="Grade 1 Orange")
    target_mean_score: Optional[float] = Field(0.0, example=75.5)

class SchoolRegistrationRequest(BaseModel):
    school_name: str = Field(..., example="Moi Educational Centre")
    county: str = Field(..., example="Nairobi")
    email: str = Field(..., example="info@moieducational.ac.ke")
    phone: str = Field(..., example="0712345678")
    number_of_students: int = Field(..., example=500)
    number_of_teachers: int = Field(..., example=20)
    headteacher_name: Optional[str] = Field(None, example="Mr. Otieno")
    dean_name: Optional[str] = Field(None, example="Ms. Wanjiku")
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