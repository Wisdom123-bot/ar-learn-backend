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

    # 1. Student basic info
    student_result = (
        db.table("students")
        .select("*, classes(name, school_id), schools(name)")
        .eq("id", student_id)
        .limit(1)
        .execute()
    )
    if not student_result.data:
        raise HTTPException(status_code=404, detail="Student not found")
    s = student_result.data[0]
    class_name = s["classes"]["name"] if s.get("classes") else ""
    school_name = s["schools"]["name"] if s.get("schools") else ""
    school_id = s["classes"]["school_id"] if s.get("classes") else ""

    # 2. Results
    results = (
        db.table("results")
        .select("*, subjects(name)")
        .eq("student_id", student_id)
        .eq("term", term)
        .eq("approval_status", "approved")
        .execute()
        .data or []
    )
    subject_scores = defaultdict(list)
    for r in results:
        subject_scores[r["subjects"]["name"]].append(r["score"])
    results_summary = []
    for subj, scores in subject_scores.items():
        results_summary.append({
            "subject": subj,
            "scores": scores,
            "average": round(sum(scores) / len(scores), 2),
        })

    # 3. Attendance
    attendance = (
        db.table("attendance")
        .select("status")
        .eq("student_id", student_id)
        .execute()
        .data or []
    )
    att_counts = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    for a in attendance:
        key = a["status"].lower()
        if key in att_counts:
            att_counts[key] += 1
    total_att = sum(att_counts.values())
    attendance_pct = round((att_counts["present"] / total_att) * 100, 1) if total_att > 0 else 0

    # 4. Discipline
    discipline = (
        db.table("discipline_records")
        .select("*")
        .eq("student_id", student_id)
        .order("incident_date", desc=True)
        .execute()
        .data or []
    )

    # 5. Fee status
    fee_result = (
        db.table("fee_balances")
        .select("*")
        .eq("student_id", student_id)
        .eq("term", term)
        .limit(1)
        .execute()
    )
    fee_data = fee_result.data[0] if fee_result.data else {"balance": 0, "cleared": True}
    payments = (
        db.table("fee_payments")
        .select("*")
        .eq("student_id", student_id)
        .eq("term", term)
        .order("payment_date", desc=True)
        .execute()
        .data or []
    )

    # 6. Class teacher remarks
    remarks = (
        db.table("class_teacher_remarks")
        .select("remark")
        .eq("student_id", student_id)
        .eq("term", term)
        .limit(1)
        .execute()
    )
    class_remark = remarks.data[0]["remark"] if remarks.data else ""

    # 7. Identify Weaknesses (Scores < 50%)
    weaknesses = [r["subject"] for r in results_summary if r["average"] < 50]

    # 8. Fetch Badges
    badges_result = db.table("student_badges")\
        .select("id, term, badges(name, icon_url, description), teachers(name)")\
        .eq("student_id", student_id)\
        .execute()
    badges = []
    for b in (badges_result.data or []):
        badges.append({
            "id": b["id"],
            "term": b["term"],
            "badge": b["badges"],
            "awarded_by_name": b["teachers"]["name"] if b.get("teachers") else "System",
        })

    return {
        "student": {
            "id": s["id"],
            "name": s["name"],
            "admission_number": s["admission_number"],
            "access_code": s["access_code"],
            "class_name": class_name,
            "school_name": school_name,
            "school_id": school_id,
        },
        "results": results_summary,
        "attendance": {
            "summary": att_counts,
            "percentage": attendance_pct,
            "total_days": total_att,
        },
        "discipline": discipline,
        "fee": {
            "balance": fee_data["balance"],
            "cleared": fee_data["cleared"],
            "payments": payments,
        },
        "class_teacher_remark": class_remark,
        "weaknesses": weaknesses,
        "badges": badges,
    }

@router.get("/{student_id}/ai-summary")
async def get_student_ai_summary(student_id: str, term: str = Query("Term 1 2025")):
    try:
        summary = await generate_student_summary(student_id, term)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
