from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.core.database import get_supabase
from app.schemas.parent import ParentLoginRequest, ParentLoginResponse
from app.services.report_service import generate_student_report_pdf
import io

router = APIRouter(prefix="/parents", tags=["parents"])


@router.post("/login", response_model=ParentLoginResponse)
async def parent_login(payload: ParentLoginRequest):
    db = get_supabase()

    # 1. Find the school by name (exact match, case-insensitive)
    school = db.table("schools").select("id, name").ilike("name", payload.school_name.strip()).execute()
    if not school.data:
        raise HTTPException(status_code=401, detail="Invalid school name")
    school_data = school.data[0]
    school_id = school_data["id"]

    # 2. Build query to find student: must belong to that school
    query = db.table("students").select("*, classes(name)").eq("school_id", school_id)

    # Match by name (case-insensitive)
    if payload.student_name:
        query = query.ilike("name", payload.student_name.strip())

    if payload.admission_number:
        query = query.eq("admission_number", payload.admission_number.strip())
    elif payload.access_code:
        query = query.eq("access_code", payload.access_code.strip())
    else:
        raise HTTPException(status_code=400, detail="Provide admission number or access code")

    result = query.execute()

    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=401, detail="Student not found with provided details")

    # If multiple students match (unlikely with admission number), take the first exact match
    student = result.data[0]

    # 3. Verify student name matches (optional strict check)
    if student["name"].strip().lower() != payload.student_name.strip().lower():
        raise HTTPException(status_code=401, detail="Student name does not match")

    # 4. Return student info
    return ParentLoginResponse(
        student_id=student["id"],
        name=student["name"],
        admission_number=student["admission_number"],
        class_name=student["classes"]["name"] if student.get("classes") else "",
        school_name=school_data["name"],
    )


@router.get("/student/{student_id}/results")
async def get_student_results(
    student_id: str,
    term: str = Query(..., description="e.g. 'Term 1 2025'"),
):
    db = get_supabase()

    student = db.table("students").select("id").eq("id", student_id).execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    results = (
        db.table("results")
        .select("*, subjects(name)")
        .eq("student_id", student_id)
        .eq("term", term)
        .eq("approval_status", "approved")
        .execute()
        .data or []
    )

    return [
        {
            "subject": r["subjects"]["name"],
            "exam_type": r["exam_type"],
            "score": r["score"],
            "remarks": r.get("remarks", ""),
        }
        for r in results
    ]


@router.get("/student/{student_id}/attendance")
async def get_student_attendance(
    student_id: str,
    term_start: str = Query(None, description="YYYY-MM-DD"),
    term_end: str = Query(None, description="YYYY-MM-DD"),
):
    db = get_supabase()

    student = db.table("students").select("id, name").eq("id", student_id).execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    query = db.table("attendance").select("*").eq("student_id", student_id)
    if term_start:
        query = query.gte("date", term_start)
    if term_end:
        query = query.lte("date", term_end)
    records = query.execute().data or []

    stats = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    for r in records:
        status_lower = r["status"].lower()
        if status_lower in stats:
            stats[status_lower] += 1

    total = sum(stats.values())
    pct = (stats["present"] / total * 100) if total > 0 else 0
    return {
        "student_name": student.data[0]["name"],
        "total_days": total,
        "attendance_pct": round(pct, 1),
        "breakdown": stats,
    }


@router.get("/student/{student_id}/fees")
async def get_student_fees(
    student_id: str,
    term: str = Query(..., description="e.g. 'Term 1 2025'"),
):
    db = get_supabase()

    student = db.table("students").select("id, name").eq("id", student_id).execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    # Reuse existing fee logic; call the fees router's function? Or duplicate.
    # We'll do a simple manual query here.
    balance = (
        db.table("fee_balances")
        .select("*")
        .eq("student_id", student_id)
        .eq("term", term)
        .execute()
    )
    current_balance = balance.data[0]["balance"] if balance.data else 0
    cleared = balance.data[0]["cleared"] if balance.data else True

    payments = (
        db.table("fee_payments")
        .select("*")
        .eq("student_id", student_id)
        .eq("term", term)
        .order("payment_date", desc=True)
        .execute()
        .data or []
    )

    return {
        "student_name": student.data[0]["name"],
        "term": term,
        "balance": current_balance,
        "cleared": cleared,
        "payments": [
            {
                "amount": p["amount"],
                "date": p["payment_date"],
                "receipt_number": p["receipt_number"],
            }
            for p in payments
        ],
    }


@router.get("/student/{student_id}/report")
async def download_student_report(
    student_id: str,
    term: str = Query(..., description="e.g. 'Term 1 2025'"),
):
    """Parent downloads their child's approved report card."""
    db = get_supabase()

    # Optional: verify student exists
    student = db.table("students").select("id").eq("id", student_id).execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        pdf_bytes = await generate_student_report_pdf(student_id, term)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{student_id}.pdf"},
    )