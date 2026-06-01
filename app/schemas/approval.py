from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class ApprovalRequest(BaseModel):
    headteacher_id: UUID = Field(..., description="Teacher ID of the headteacher")
    class_id: UUID
    term: str = Field(..., example="Term 1 2025")
    action: str = Field(..., pattern="^(approve|reject)$")
    remarks: Optional[str] = Field("", example="Approved after review.")