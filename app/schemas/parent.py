from pydantic import BaseModel
from uuid import UUID
from typing import Optional

class ParentLoginRequest(BaseModel):
    school_name: str
    student_name: str
    admission_number: Optional[str] = None
    access_code: Optional[str] = None  # at least one of the two must be provided

class ParentLoginResponse(BaseModel):
    student_id: UUID
    name: str
    admission_number: str
    class_name: str
    school_name: str