from fastapi import APIRouter, HTTPException, Query
from app.core.database import get_supabase
from collections import defaultdict
from app.services.ai_summary_service import generate_student_summary

router = APIRouter(prefix="/students", tags=["students"])


@router.get("/by-admission")
async def get_student_by_admission(admission: str = Query(...)):
    db = get_supabase()
    result = (
        db.table("students")
        .select("id, name, admission_number, class_id")
        .eq("admission_number", admission)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Student not found")
    return result.data[0]
@router.get("/search")
async def search_students(q: str = Query(..., min_length=2)):
    db = get_supabase()
    # Search by name OR admission number (case‑insensitive)
    result = (
        db.table("students")
        .select("id, name, admission_number, classes(name)")
        .or_(f"name.ilike.%{q}%,admission_number.ilike.%{q}%")
        .limit(10)
        .execute()
        .data or []
    )
    # Flatten class name
    for s in result:
        if s.get("classes"):
            s["class_name"] = s["classes"]["name"]
            del s["classes"]
        else:
            s["class_name"] = ""
    return result

@router.get("/school/{school_id}")
async def list_school_students(school_id: str):
    db = get_supabase()
    students = (
        db.table("students")
        .select("id, name, admission_number, access_code, classes(name)")
        .eq("school_id", school_id)
        .order("name")
        .execute()
        .data or []
    )
    for s in students:
        if s.get("classes"):
            s["class_name"] = s["classes"]["name"]
            del s["classes"]
        else:
            s["class_name"] = ""
    return students


@router.get("/{student_id}/profile")
async def get_student_profile(student_id: str, term: str = Query("Term 1 2025")):
    db = get_supabase()

    # 1. Fetch basic student info
    student_query = (
        db.table("students")
        .select("*, classes(name, school_id), schools(name)")
        .eq("id", student_id)
        .single()
        .execute()
    )

    if not student_query.data:
        raise HTTPException(status_code=404, detail="Student not found")
    
    s = student_query.data

    # 2. Fetch linked records separately for maximum robustness (Avoiding PGRST108 errors)
    
    # Results
    results = []
    try:
        res_query = db.table("results").select("*, subjects(name)").eq("student_id", student_id).eq("term", term).eq("approval_status", "approved").execute()
        results = res_query.data or []
    except Exception: pass

    # Attendance
    attendance = []
    try:
        att_query = db.table("attendance").select("status").eq("student_id", student_id).execute()
        attendance = att_query.data or []
    except Exception: pass

    # Discipline
    discipline = []
    try:
        disc_query = db.table("discipline_records").select("*").eq("student_id", student_id).execute()
        discipline = disc_query.data or []
    except Exception: pass

    # Fees
    fee_balance_data = {"balance": 0, "cleared": True}
    fee_payments = []
    try:
        bal_query = db.table("fee_balances").select("*").eq("student_id", student_id).eq("term", term).maybe_single().execute()
        if bal_query.data:
            fee_balance_data = bal_query.data
            
        pay_query = db.table("fee_payments").select("*").eq("student_id", student_id).eq("term", term).execute()
        fee_payments = pay_query.data or []
    except Exception: pass

    # Badges
    badges = []
    try:
        badge_query = db.table("student_badges").select("*, badges(name, icon_url, description), teachers(name)").eq("student_id", student_id).eq("term", term).execute()
        for b in (badge_query.data or []):
            badges.append({
                "id": b["id"],
                "term": b["term"],
                "badge": b["badges"],
                "awarded_by_name": b["teachers"]["name"] if b.get("teachers") else "System",
            })
    except Exception: pass

    # Process Results
    results_summary = []
    subject_scores = defaultdict(list)
    for r in results:
        subject_scores[r["subjects"]["name"]].append(r["score"])
    for subj, scores in subject_scores.items():
        results_summary.append({
            "subject": subj,
            "scores": scores,
            "average": round(sum(scores) / len(scores), 2),
        })

    # Process Attendance
    att_counts = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    for a in attendance:
        key = a["status"].lower()
        if key in att_counts:
            att_counts[key] += 1
    total_att = sum(att_counts.values())
    attendance_pct = round((att_counts["present"] / total_att) * 100, 1) if total_att > 0 else 0

    # Fetch class teacher remarks separately for robustness
    class_teacher_remark = ""
    try:
        remark_query = (
            db.table("class_teacher_remarks")
            .select("remark")
            .eq("student_id", student_id)
            .eq("term", term)
            .limit(1)
            .execute()
        )
        if remark_query.data:
            class_teacher_remark = remark_query.data[0]["remark"]
    except Exception:
        pass

    return {
        "student": {
            "id": s["id"],
            "name": s["name"],
            "admission_number": s["admission_number"],
            "class_name": s["classes"]["name"] if s.get("classes") else "",
            "school_name": s["schools"]["name"] if s.get("schools") else "",
            "school_id": s["classes"]["school_id"] if s.get("classes") else "",
        },
        "results": results_summary,
        "attendance": {
            "summary": att_counts,
            "percentage": attendance_pct,
            "total_days": total_att,
        },
        "discipline": discipline,
        "fee": {
            "balance": fee_balance_data["balance"],
            "cleared": fee_balance_data["cleared"],
            "payments": fee_payments,
        },
        "class_teacher_remark": class_teacher_remark,
        "weaknesses": [r["subject"] for r in results_summary if r["average"] < 50],
        "badges": badges,
    }

@router.get("/{student_id}/ai-summary")
async def get_student_ai_summary(student_id: str, term: str = Query("Term 1 2025")):
    try:
        summary = await generate_student_summary(student_id, term)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
