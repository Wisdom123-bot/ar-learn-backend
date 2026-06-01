from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.core.database import get_supabase
from app.services.remark_generator import detect_risk_flags
from app.schemas.risk import StudentRiskProfile

router = APIRouter(prefix="/risk", tags=["risk"])


def get_previous_term(term: str) -> Optional[str]:
    """Given 'Term X YYYY', return 'Term X-1 YYYY' or 'Term 3 YYYY-1'."""
    try:
        parts = term.split(" ")
        t_num = int(parts[1])
        year = int(parts[2])
        if t_num > 1:
            return f"Term {t_num - 1} {year}"
        else:
            return f"Term 3 {year - 1}"
    except Exception:
        return None


@router.get("/class/{class_id}", response_model=List[StudentRiskProfile])
async def class_risk_analysis(
    class_id: str,
    term: str = Query(..., description="Current term, e.g. 'Term 1 2025'"),
    attendance_start: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    attendance_end: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    db = get_supabase()

    # 1. Verify class exists
    cls = db.table("classes").select("id, name").eq("id", class_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")
    class_name = cls.data[0]["name"]

    # 2. Get all students in this class
    students = db.table("students").select("*").eq("class_id", class_id).execute().data
    if not students:
        return []

    student_ids = [s["id"] for s in students]
    student_map = {s["id"]: s for s in students}

    # 3. Fetch current term results for these students
    current_results = (
        db.table("results")
        .select("*")
        .in_("student_id", student_ids)
        .eq("term", term)
        .execute()
        .data or []
    )

    # Group by student_id and subject_id, compute average score
    # Also need subject names
    from collections import defaultdict
    student_subject_scores = defaultdict(lambda: defaultdict(list))
    for r in current_results:
        student_subject_scores[r["student_id"]][r["subject_id"]].append(r["score"])

    # Get all subject names (cache in dict)
    all_subject_ids = set()
    for r in current_results:
        all_subject_ids.add(r["subject_id"])
    subject_name_map = {}
    if all_subject_ids:
        subs = db.table("subjects").select("id, name").in_("id", list(all_subject_ids)).execute().data
        for sub in subs:
            subject_name_map[sub["id"]] = sub["name"]

    # Build current results per student as list of dicts
    student_current = {}
    for sid, sub_scores in student_subject_scores.items():
        subject_list = []
        for sub_id, scores in sub_scores.items():
            avg = sum(scores) / len(scores)
            subject_list.append({
                "subject_name": subject_name_map.get(sub_id, sub_id),
                "score": round(avg, 1),
            })
        student_current[sid] = subject_list

    # 4. Fetch previous term results for trend detection
    prev_term = get_previous_term(term)
    student_previous = {}
    if prev_term:
        prev_results = (
            db.table("results")
            .select("*")
            .in_("student_id", student_ids)
            .eq("term", prev_term)
            .execute()
            .data or []
        )
        prev_student_subject_scores = defaultdict(lambda: defaultdict(list))
        for r in prev_results:
            prev_student_subject_scores[r["student_id"]][r["subject_id"]].append(r["score"])
        for sid, sub_scores in prev_student_subject_scores.items():
            subject_list = []
            for sub_id, scores in sub_scores.items():
                avg = sum(scores) / len(scores)
                subject_list.append({
                    "subject_name": subject_name_map.get(sub_id, sub_id),
                    "score": round(avg, 1),
                })
            student_previous[sid] = subject_list

    # 5. Attendance percentages (if dates provided)
    student_attendance = {}
    if attendance_start and attendance_end:
        att_records = (
            db.table("attendance")
            .select("*")
            .in_("student_id", student_ids)
            .gte("date", attendance_start)
            .lte("date", attendance_end)
            .execute()
            .data or []
        )
        att_counts = defaultdict(lambda: {"present": 0, "total": 0})
        for rec in att_records:
            sid = rec["student_id"]
            att_counts[sid]["total"] += 1
            if rec["status"].lower() == "present":
                att_counts[sid]["present"] += 1
        for sid, counts in att_counts.items():
            if counts["total"] > 0:
                student_attendance[sid] = (counts["present"] / counts["total"]) * 100

    # 6. Generate risk profiles
    profiles = []
    for s in students:
        sid = s["id"]
        current = student_current.get(sid, [])
        previous = student_previous.get(sid, None)
        att_pct = student_attendance.get(sid)

        # Compute overall current mean
        overall_mean = None
        if current:
            overall_mean = sum(sub["score"] for sub in current) / len(current)

        # Run risk flags
        flags = detect_risk_flags(sid, current, previous, att_pct)

        profiles.append(StudentRiskProfile(
            student_id=sid,
            student_name=s["name"],
            admission_number=s["admission_number"],
            class_name=class_name,
            current_mean=round(overall_mean, 2) if overall_mean is not None else None,
            attendance_pct=round(att_pct, 1) if att_pct is not None else None,
            risk_flags=flags,
        ))

    # Sort: students with most risk flags first
    profiles.sort(key=lambda x: len(x.risk_flags), reverse=True)
    return profiles