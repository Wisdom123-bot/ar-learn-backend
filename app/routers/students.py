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

    # Optimized query to fetch main student details and linked records
    # Note: class_teacher_remarks and fee_payments are fetched separately to avoid PGRST108 errors
    # if the database relationship isn't properly detected by PostgREST cache.
    query = (
        db.table("students")
        .select("""
            *,
            classes(name, school_id),
            schools(name),
            results(*, subjects(name)),
            attendance(status),
            discipline_records(*),
            fee_balances(*),
            student_badges(id, term, badges(name, icon_url, description), teachers(name))
        """)
        .eq("id", student_id)
        .eq("results.term", term)
        .eq("results.approval_status", "approved")
        .eq("fee_balances.term", term)
        .limit(1)
        .execute()
    )

    if not query.data:
        raise HTTPException(status_code=404, detail="Student not found")
    
    s = query.data[0]

    # Fetch fee payments separately for robustness
    fee_payments = []
    try:
        payments_query = (
            db.table("fee_payments")
            .select("*")
            .eq("student_id", student_id)
            .eq("term", term)
            .execute()
        )
        fee_payments = payments_query.data or []
    except Exception:
        pass

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
        # Fallback if table doesn't exist or query fails
        pass
    
    # Process results
    results_summary = []
    subject_scores = defaultdict(list)
    for r in (s.get("results") or []):
        subject_scores[r["subjects"]["name"]].append(r["score"])
    for subj, scores in subject_scores.items():
        results_summary.append({
            "subject": subj,
            "scores": scores,
            "average": round(sum(scores) / len(scores), 2),
        })

    # Process attendance
    att_counts = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    for a in (s.get("attendance") or []):
        key = a["status"].lower()
        if key in att_counts:
            att_counts[key] += 1
    total_att = sum(att_counts.values())
    attendance_pct = round((att_counts["present"] / total_att) * 100, 1) if total_att > 0 else 0

    # Process fees
    fee_data = s["fee_balances"][0] if s.get("fee_balances") else {"balance": 0, "cleared": True}
    
    # Process badges
    badges = []
    for b in (s.get("student_badges") or []):
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
        "discipline": s.get("discipline_records") or [],
        "fee": {
            "balance": fee_data["balance"],
            "cleared": fee_data["cleared"],
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
