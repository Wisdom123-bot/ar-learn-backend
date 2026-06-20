import random
import string
import uuid
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from app.core.database import get_supabase
from app.services.notification_service import create_notification
from app.services.audit_service import log_action
from app.schemas.fee import FeeBalanceCreate, FeePaymentCreate, FeeStatus, TermFeeRequest
from app.dependencies import get_current_user

router = APIRouter(prefix="/fees", tags=["fees"])


def generate_receipt_number() -> str:
    """
    Generates a more robust unique receipt number.
    Format: RCPT-XXXXXX (6 alphanumeric chars)
    """
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=6))
    return f"RCPT-{code}"


def check_admin_role(user: dict):
    if user.get("role") not in ["headteacher", "dean"]:
        raise HTTPException(status_code=403, detail="Access denied: Admin role required")


@router.post("/balance/add")
async def add_fee_balance(
    payload: FeeBalanceCreate,
    current_user: dict = Depends(get_current_user)
):
    check_admin_role(current_user)
    db = get_supabase()
    
    # Use upsert to handle both creation and updates safely
    # Note: student_id + term must have a unique constraint in Postgres for this to be truly atomic
    data = {
        "student_id": str(payload.student_id),
        "term": payload.term,
        "balance": payload.balance,
        "cleared": payload.balance <= 0,
    }
    
    try:
        result = db.table("fee_balances").upsert(data, on_conflict="student_id,term").execute()
        
        # Audit log
        log_action(
            school_id=current_user["school_id"],
            action="FEE_BALANCE_ADJUSTED",
            actor_id=current_user["id"],
            actor_name=current_user["name"],
            entity_type="fee_balance",
            entity_id=str(payload.student_id),
            new_value=data
        )
        
        create_notification(
            school_id=current_user["school_id"],
            teacher_id=current_user["id"],
            title="Manual Fee Adjustment",
            message=f"Admin manually set balance for Student {payload.student_id} to KES {payload.balance}.",
            category="fee"
        )
        
        return {"message": "Fee balance updated", "data": result.data[0] if result.data else {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/payment/record")
async def record_payment(
    payload: FeePaymentCreate,
    current_user: dict = Depends(get_current_user)
):
    check_admin_role(current_user)
    db = get_supabase()

    # 1. Verify student exists and get school context
    student_res = db.table("students").select("id, name, admission_number, school_id").eq("id", str(payload.student_id)).execute()
    if not student_res.data:
        raise HTTPException(status_code=404, detail="Student not found")
    student = student_res.data[0]

    # 2. Get current balance (needed for calculation)
    # Note: To be 100% atomic against race conditions, we would ideally use a stored procedure (RPC)
    # but since Supabase Python client doesn't support increment/decrement expressions directly in .update(),
    # we'll use a transaction-like approach or just ensure we fetch and update in sequence.
    balance_record = (
        db.table("fee_balances")
        .select("*")
        .eq("student_id", str(payload.student_id))
        .eq("term", payload.term)
        .execute()
    )

    if not balance_record.data:
        # Create initial record if missing
        bal_data = {
            "student_id": str(payload.student_id),
            "term": payload.term,
            "balance": 0,
            "cleared": True,
        }
        db.table("fee_balances").insert(bal_data).execute()
        current_bal_amount = 0
        balance_id = None # will fetch later or rely on upsert
    else:
        current_bal_amount = balance_record.data[0]["balance"]
        balance_id = balance_record.data[0]["id"]

    # 3. Generate unique receipt
    receipt = generate_receipt_number()
    # Retry a few times if collision (rare with 6 chars)
    for _ in range(3):
        existing = db.table("fee_payments").select("id").eq("receipt_number", receipt).execute()
        if not existing.data:
            break
        receipt = generate_receipt_number()

    # 4. Insert Payment and Update Balance
    payment_data = {
        "student_id": str(payload.student_id),
        "amount": payload.amount,
        "payment_date": payload.payment_date.isoformat(),
        "receipt_number": receipt,
        "recorded_by": str(current_user["id"]),
        "term": payload.term,
    }
    
    try:
        db.table("fee_payments").insert(payment_data).execute()

        new_balance = max(0, current_bal_amount - payload.amount)
        cleared = new_balance <= 0
        
        # Atomically update balance
        db.table("fee_balances").update({
            "balance": new_balance, 
            "cleared": cleared
        }).eq("student_id", str(payload.student_id)).eq("term", payload.term).execute()

        # Audit log
        log_action(
            school_id=student["school_id"],
            action="FEE_PAYMENT_RECORDED",
            actor_id=current_user["id"],
            actor_name=current_user["name"],
            entity_type="fee_payment",
            entity_id=receipt,
            new_value=payment_data
        )

        # Notify headteacher
        admins = db.table("teachers").select("id").eq("school_id", student["school_id"]).in_("role", ["headteacher"]).execute().data or []
        for admin in admins:
            create_notification(
                school_id=student["school_id"],
                teacher_id=admin["id"],
                title="Fee Payment Received",
                message=f"{student['name']} (Adm: {student['admission_number']}) paid KES {payload.amount}. Receipt: {receipt}.",
                category="fee"
            )

        return {
            "message": "Payment recorded", 
            "receipt_number": receipt, 
            "new_balance": new_balance, 
            "cleared": cleared
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process payment: {str(e)}")


@router.get("/student/{student_id}", response_model=FeeStatus)
async def get_student_fees(
    student_id: str, 
    term: str = Query(...),
    current_user: dict = Depends(get_current_user)
):
    # Any teacher in the school can view student fees
    db = get_supabase()
    student = db.table("students").select("id, name, school_id").eq("id", student_id).execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")
    
    if student.data[0]["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied: Student belongs to another school")

    balance_record = (
        db.table("fee_balances")
        .select("*")
        .eq("student_id", student_id)
        .eq("term", term)
        .maybe_single()
        .execute()
    )
    
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

    bal = balance_record.data
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
async def class_fee_status(
    class_id: str, 
    term: str = Query(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Optimized class-wide fee status using JOINs and batching.
    No more N+1 query pattern.
    """
    db = get_supabase()
    
    # 1. Verify class belongs to user's school
    cls_check = db.table("classes").select("school_id").eq("id", class_id).single().execute()
    if not cls_check.data or cls_check.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # 2. Fetch all students in class
    students = db.table("students").select("id, name").eq("class_id", class_id).execute().data or []
    if not students:
        return []
    
    student_ids = [s["id"] for s in students]
    student_names = {s["id"]: s["name"] for s in students}

    # 3. Batch fetch balances for all students
    balances = db.table("fee_balances").select("*").in_("student_id", student_ids).eq("term", term).execute().data or []
    balance_map = {b["student_id"]: b for b in balances}

    # 4. Batch fetch payments for all students
    payments = db.table("fee_payments").select("*").in_("student_id", student_ids).eq("term", term).execute().data or []
    payment_map = {}
    for p in payments:
        sid = p["student_id"]
        if sid not in payment_map: payment_map[sid] = []
        payment_map[sid].append(p)

    # 5. Assemble result
    result = []
    for sid in student_ids:
        bal = balance_map.get(sid, {"balance": 0, "cleared": True})
        pay_list = payment_map.get(sid, [])
        total_paid = sum(p["amount"] for p in pay_list)
        
        result.append(FeeStatus(
            student_id=sid,
            student_name=student_names[sid],
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
            } for p in pay_list],
            total_paid=total_paid,
        ))
        
    return result


@router.post("/term-fee")
async def set_term_fee(
    payload: TermFeeRequest,
    school_id: str = Query(...),
    term: str = Query(...),
    current_user: dict = Depends(get_current_user)
):
    check_admin_role(current_user)
    if school_id != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    db = get_supabase()

    # 1. Store the term fee definition
    data = {"school_id": school_id, "term": term, "amount": payload.amount}
    db.table("term_fees").upsert(data, on_conflict="school_id,term").execute()

    # 2. Get target students
    query = db.table("students").select("id").eq("school_id", school_id)
    if payload.class_id:
        query = query.eq("class_id", str(payload.class_id))
    
    students = query.execute().data or []
    if not students:
        return {"message": "No students found", "count": 0}

    # 3. Batch upsert fee_balances
    upsert_data = []
    for s in students:
        upsert_data.append({
            "student_id": s["id"],
            "term": term,
            "balance": payload.amount,
            "cleared": payload.amount <= 0
        })

    # Atomically bill all students
    db.table("fee_balances").upsert(upsert_data, on_conflict="student_id,term").execute()

    return {"message": f"Term fee set for {len(students)} students", "count": len(students)}


@router.get("/defaulters")
async def get_defaulters(
    school_id: str = Query(...),
    current_term: str = Query(...),
    previous_term: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    if school_id != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

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
async def get_term_fee(
    school_id: str = Query(...), 
    term: str = Query(...),
    current_user: dict = Depends(get_current_user)
):
    if school_id != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    db = get_supabase()
    result = db.table("term_fees").select("amount").eq("school_id", school_id).eq("term", term).maybe_single().execute()
    if result.data:
        return {"amount": result.data["amount"]}
    return {"amount": 0}

@router.get("/deficit")
async def get_school_deficit(
    school_id: str = Query(...), 
    term: str = Query(...),
    current_user: dict = Depends(get_current_user)
):
    if school_id != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    db = get_supabase()
    
    tf_result = db.table("term_fees").select("amount").eq("school_id", school_id).eq("term", term).maybe_single().execute()
    term_fee = tf_result.data["amount"] if tf_result.data else 0

    if term_fee == 0:
        return {"term_fee": 0, "total_expected": 0, "total_collected": 0, "deficit": 0}

    students = db.table("students").select("id").eq("school_id", school_id).execute().data
    if not students:
        return {"term_fee": term_fee, "total_expected": 0, "total_collected": 0, "deficit": 0}

    student_ids = [s["id"] for s in students]
    payments = db.table("fee_payments").select("amount").in_("student_id", student_ids).eq("term", term).execute().data or []
    total_collected = sum(p["amount"] for p in payments)

    total_expected = len(students) * term_fee
    deficit = max(0.0, float(total_expected) - float(total_collected))

    return {
        "term_fee": term_fee,
        "total_expected": total_expected,
        "total_collected": total_collected,
        "deficit": deficit,
        "student_count": len(students)
    }
