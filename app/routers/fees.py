import random
import string
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.core.database import get_supabase
from app.services.notification_service import create_notification
from app.schemas.fee import FeeBalanceCreate, FeePaymentCreate, FeeStatus

router = APIRouter(prefix="/fees", tags=["fees"])


def generate_receipt_number() -> str:
    letters = ''.join(random.choices(string.ascii_uppercase, k=2))
    digits = ''.join(random.choices(string.digits, k=4))
    return f"RCPT-{letters}{digits}"


@router.post("/balance/add")
async def add_fee_balance(payload: FeeBalanceCreate):
    db = get_supabase()
    existing = (
        db.table("fee_balances")
        .select("id")
        .eq("student_id", str(payload.student_id))
        .eq("term", payload.term)
        .execute()
    )
    if existing.data:
        db.table("fee_balances").update({"balance": payload.balance}).eq("id", existing.data[0]["id"]).execute()
        return {"message": "Fee balance updated"}
    else:
        data = {
            "student_id": str(payload.student_id),
            "term": payload.term,
            "balance": payload.balance,
            "cleared": False,
        }
        db.table("fee_balances").insert(data).execute()
        return {"message": "Fee balance added"}


@router.post("/payment/record")
async def record_payment(payload: FeePaymentCreate):
    db = get_supabase()

    student = db.table("students").select("id, name, admission_number, school_id").eq("id", str(payload.student_id)).execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    balance_record = (
        db.table("fee_balances")
        .select("*")
        .eq("student_id", str(payload.student_id))
        .eq("term", payload.term)
        .execute()
    )

    if not balance_record.data:
        bal_data = {
            "student_id": str(payload.student_id),
            "term": payload.term,
            "balance": 0,
            "cleared": False,
        }
        db.table("fee_balances").insert(bal_data).execute()
        balance_record = (
            db.table("fee_balances")
            .select("*")
            .eq("student_id", str(payload.student_id))
            .eq("term", payload.term)
            .execute()
        )

    balance = balance_record.data[0]

    receipt = generate_receipt_number()
    existing_rec = db.table("fee_payments").select("id").eq("receipt_number", receipt).execute()
    while existing_rec.data:
        receipt = generate_receipt_number()
        existing_rec = db.table("fee_payments").select("id").eq("receipt_number", receipt).execute()

    payment_data = {
        "student_id": str(payload.student_id),
        "amount": payload.amount,
        "payment_date": payload.payment_date.isoformat(),
        "receipt_number": receipt,
        "recorded_by": str(payload.recorded_by) if payload.recorded_by else None,
        "term": payload.term,
    }
    db.table("fee_payments").insert(payment_data).execute()

    new_balance = max(0, balance["balance"] - payload.amount)
    cleared = new_balance <= 0
    db.table("fee_balances").update({"balance": new_balance, "cleared": cleared}).eq("id", balance["id"]).execute()

    # Notify headteacher
    school_id = student.data[0]["school_id"]
    admins = db.table("teachers").select("id").eq("school_id", school_id).in_("role", ["headteacher"]).execute().data or []
    for admin in admins:
        create_notification(
            school_id=school_id,
            teacher_id=admin["id"],
            title="Fee Payment Received",
            message=f"{student.data[0]['name']} (Adm: {student.data[0]['admission_number']}) paid KES {payload.amount}. Receipt: {receipt}.",
            category="fee"
        )

    return {"message": "Payment recorded", "receipt_number": receipt, "new_balance": new_balance, "cleared": cleared}


@router.get("/student/{student_id}", response_model=FeeStatus)
async def get_student_fees(student_id: str, term: str = Query(...)):
    db = get_supabase()
    student = db.table("students").select("id, name").eq("id", student_id).execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    balance_record = (
        db.table("fee_balances")
        .select("*")
        .eq("student_id", student_id)
        .eq("term", term)
        .execute()
    )
    if not balance_record.data:
        return FeeStatus(
            student_id=student_id,
            student_name=student.data[0]["name"],
            term=term,
            balance=0,
            cleared=True,
            payments=[],
            total_paid=0,
        )

    bal = balance_record.data[0]
    payments = (
        db.table("fee_payments")
        .select("*")
        .eq("student_id", student_id)
        .eq("term", term)
        .order("payment_date", desc=True)
        .execute()
        .data or []
    )
    total_paid = sum(p["amount"] for p in payments)

    return FeeStatus(
        student_id=student_id,
        student_name=student.data[0]["name"],
        term=term,
        balance=bal["balance"],
        cleared=bal["cleared"],
        payments=[{
            "id": p["id"],
            "student_id": p["student_id"],
            "amount": p["amount"],
            "payment_date": p["payment_date"],
            "receipt_number": p["receipt_number"],
            "term": p["term"],
        } for p in payments],
        total_paid=total_paid,
    )


@router.get("/class/{class_id}", response_model=List[FeeStatus])
async def class_fee_status(class_id: str, term: str = Query(...)):
    db = get_supabase()
    cls = db.table("classes").select("id").eq("id", class_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")

    students = db.table("students").select("id").eq("class_id", class_id).execute().data or []
    result = []
    for s in students:
        try:
            fee = await get_student_fees(s["id"], term)
            result.append(fee)
        except Exception:
            pass
    return result