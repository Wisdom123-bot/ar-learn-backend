import random
import string
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.core.database import get_supabase
from pydantic import BaseModel
from app.services.notification_service import create_notification
from app.schemas.fee import FeeBalanceCreate, FeePaymentCreate, FeeStatus, TermFeeRequest

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


@router.post("/term-fee")
async def set_term_fee(
    payload: TermFeeRequest,
    school_id: str = Query(...),
    term: str = Query(...),
):
    db = get_supabase()

    # 1. Store the term fee definition
    existing = db.table("term_fees").select("id").eq("school_id", school_id).eq("term", term).execute()
    data = {"school_id": school_id, "term": term, "amount": payload.amount}
    if existing.data:
        db.table("term_fees").update(data).eq("id", existing.data[0]["id"]).execute()
    else:
        db.table("term_fees").insert(data).execute()

    # 2. Get students
    query = db.table("students").select("id").eq("school_id", school_id)
    if payload.class_id:
        query = query.eq("class_id", str(payload.class_id))
    
    students = query.execute().data or []
    if not students:
        return {"message": "No students found", "count": 0}

    # 3. Batch upsert fee_balances
    # Note: Supabase doesn't have a true 'upsert' that handles 'WHERE student_id=X AND term=Y' 
    # for a list in one go easily without unique constraints. 
    # We'll do a batch insert and handle conflicts if possible, or simple batch update.
    # To keep it safe and fast, we'll use a RPC or a list of dicts for upsert if the table has a unique constraint.
    
    upsert_data = []
    for s in students:
        upsert_data.append({
            "student_id": s["id"],
            "term": term,
            "balance": payload.amount,
            "cleared": payload.amount <= 0
        })

    # Assuming student_id + term is UNIQUE in fee_balances
    db.table("fee_balances").upsert(upsert_data, on_conflict="student_id,term").execute()

    return {"message": f"Term fee set to KES {payload.amount:,.2f} for {len(students)} students", "count": len(students)}


@router.get("/defaulters")
async def get_defaulters(
    school_id: str = Query(...),
    current_term: str = Query(...),
    previous_term: Optional[str] = Query(None)
):
    db = get_supabase()
    
    # Get all students in school
    students = db.table("students").select("id, name, admission_number, class_id, classes(name)").eq("school_id", school_id).execute().data or []
    student_map = {s["id"]: s for s in students}
    student_ids = list(student_map.keys())

    if not student_ids:
        return {"current_term": [], "previous_term": []}

    # Fetch balances for current term
    current_balances = db.table("fee_balances").select("*").in_("student_id", student_ids).eq("term", current_term).gt("balance", 0).execute().data or []
    
    # Fetch balances for previous term
    prev_balances = []
    if previous_term:
        prev_balances = db.table("fee_balances").select("*").in_("student_id", student_ids).eq("term", previous_term).gt("balance", 0).execute().data or []

    def format_list(balances):
        res = []
        for b in balances:
            s = student_map.get(b["student_id"])
            if s:
                res.append({
                    "student_name": s["name"],
                    "admission_number": s["admission_number"],
                    "class_name": s["classes"]["name"] if s.get("classes") else "Unknown",
                    "balance": b["balance"]
                })
        return res

    return {
        "current_term": format_list(current_balances),
        "previous_term": format_list(prev_balances)
    }

@router.get("/term-fee")
async def get_term_fee(school_id: str = Query(...), term: str = Query(...)):
    db = get_supabase()
    result = db.table("term_fees").select("amount").eq("school_id", school_id).eq("term", term).single().execute()
    if result.data:
        return {"amount": result.data["amount"]}
    return {"amount": 0}

@router.get("/deficit")
async def get_school_deficit(school_id: str = Query(...), term: str = Query(...)):
    db = get_supabase()
    # Get term fee – safely handle missing row
    tf_result = db.table("term_fees").select("amount").eq("school_id", school_id).eq("term", term).limit(1).execute()
    term_fee = tf_result.data[0]["amount"] if tf_result.data else 0

    if term_fee == 0:
        return {"term_fee": 0, "total_expected": 0, "total_collected": 0, "deficit": 0}

    # Get all students of the school
    students = db.table("students").select("id").eq("school_id", school_id).execute().data
    if not students:
        return {"term_fee": term_fee, "total_expected": 0, "total_collected": 0, "deficit": 0}

    student_ids = [s["id"] for s in students]
    # Get all payments for this term
    payments = db.table("fee_payments").select("amount").in_("student_id", student_ids).eq("term", term).execute().data or []
    total_collected = sum(p["amount"] for p in payments)

    total_expected = len(students) * term_fee
    deficit = max(0, total_expected - total_collected)

    return {
        "term_fee": term_fee,
        "total_expected": total_expected,
        "total_collected": total_collected,
        "deficit": deficit,
        "student_count": len(students)
    }