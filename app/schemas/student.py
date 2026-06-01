from pydantic import BaseModel
from uuid import UUID

class StudentBrief(BaseModel):
    id: UUID
    name: str
    admission_number: str
    class_id: UUID
    class_name: str

    class Config:
        from_attributes = True