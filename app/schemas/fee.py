from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import date


class FeeBalanceCreate(BaseModel):
    student_id: UUID
    term: str = Field(..., example="Term 1 2025")
    balance: float = Field(..., ge=0, example=15000.0)


class FeePaymentCreate(BaseModel):
    student_id: UUID
    amount: float = Field(..., gt=0, example=5000.0)
    term: str = Field(..., example="Term 1 2025")
    payment_date: date = Field(default_factory=date.today)
    recorded_by: Optional[UUID] = None   # teacher/admin who recorded


class FeePaymentResponse(BaseModel):
    id: UUID
    student_id: UUID
    amount: float
    payment_date: date
    receipt_number: str
    term: str


class FeeStatus(BaseModel):
    student_id: UUID
    student_name: str
    term: str
    balance: float
    cleared: bool
    payments: List[FeePaymentResponse] = []
    total_paid: float = 0.0