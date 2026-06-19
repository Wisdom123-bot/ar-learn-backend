from app.services.analytics_service import get_school_overview
from app.services.teacher_analytics_service import compute_teacher_value_add
from app.core.database import get_supabase
from app.utils.cache import get_cache, set_cache
from collections import defaultdict

def get_headteacher_dashboard(school_id: str, term: str, previous_term: str = None) -> dict:
    cache_key = f"ht_dashboard:{school_id}:{term}:{previous_term}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    db = get_supabase()

    # Get school overview (optimized to use classes)
    overview = get_school_overview(school_id)

    # Get teacher performance (optimized to use classes)
    teacher_perf = compute_teacher_value_add(school_id, term, previous_term)
    top_teachers = teacher_perf[:5]
    bottom_teachers = teacher_perf[-5:] if len(teacher_perf) >= 5 else []
    bottom_teachers = sorted(bottom_teachers, key=lambda x: x["value_add"] if x["value_add"] is not None else -999)

    # Get all classes for this school
    classes = db.table("classes").select("id").eq("school_id", school_id).execute().data or []
    class_ids = [c["id"] for c in classes]
    
    risk_count = 0
    risk_sample = []
    attendance_summary = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    total_outstanding = 0
    total_cleared = 0
    previous_term_outstanding = 0
    cbc_summary = []

    if class_ids:
        # 1. Academic Risk
        results = db.table("results").select("student_id, score").eq("term", term).in_("class_id", class_ids).execute().data or []
        student_scores = defaultdict(list)
        for r in results:
            student_scores[r["student_id"]].append(r["score"])
        
        at_risk_student_ids = []
        for sid, scores in student_scores.items():
            avg = sum(scores) / len(scores)
            if avg < 50:
                risk_count += 1
                if len(risk_sample) < 5:
                    at_risk_student_ids.append(sid)
        
        if at_risk_student_ids:
            risk_students_data = db.table("students").select("id, name").in_("id", at_risk_student_ids).execute().data or []
            risk_students_map = {s["id"]: s["name"] for s in risk_students_data}
            for sid in at_risk_student_ids:
                if sid in risk_students_map:
                    avg = sum(student_scores[sid]) / len(student_scores[sid])
                    risk_sample.append({
                        "student_id": sid,
                        "student_name": risk_students_map[sid],
                        "mean_score": round(avg, 2)
                    })

        # 2. Attendance (use class_id)
        att = db.table("attendance").select("status").in_("class_id", class_ids).execute().data or []
        for a in att:
            status_lower = a["status"].lower()
            if status_lower in attendance_summary:
                attendance_summary[status_lower] += 1

        # 3. Fees (Use joined filtering to avoid large student_id lists)
        try:
            fee_balances = db.table("fee_balances").select("balance, cleared, students!inner(school_id)").eq("students.school_id", school_id).eq("term", term).execute().data or []
            total_outstanding = sum(f["balance"] for f in fee_balances)
            total_cleared = sum(1 for f in fee_balances if f["cleared"])

            if previous_term:
                prev_balances = db.table("fee_balances").select("balance, students!inner(school_id)").eq("students.school_id", school_id).eq("term", previous_term).gt("balance", 0).execute().data or []
                previous_term_outstanding = sum(b["balance"] for b in prev_balances)
        except Exception:
            # Fallback if joined query fails for some reason
            total_outstanding = 0
            total_cleared = 0
            previous_term_outstanding = 0

        # 4. CBC (Use class_id if possible, or just skip if too slow)
        try:
            cbc = db.table("cbc_assessments").select("competency_id, level, competencies(name)").in_("student_id", [sid for sid in student_scores.keys()]).execute().data or []
            comp_levels = defaultdict(lambda: {"BE": 0, "AE": 0, "name": ""})
            for c in cbc:
                cid = c["competency_id"]
                comp_levels[cid]["name"] = c["competencies"]["name"] if c.get("competencies") else ""
                if c["level"] in ("BE", "AE"):
                    comp_levels[cid][c["level"]] += 1
            weakest = sorted(comp_levels.items(), key=lambda x: x[1]["BE"] + x[1]["AE"], reverse=True)[:3]
            cbc_summary = [{"competency": v["name"], "BE": v["BE"], "AE": v["AE"]} for _, v in weakest]
        except Exception:
            cbc_summary = []

    data = {
        "school_mean": overview.get("school_mean", 0),
        "best_class": overview.get("best_class"),
        "worst_class": overview.get("worst_class"),
        "best_subject": overview.get("best_subject"),
        "worst_subject": overview.get("worst_subject"),
        "top_teachers": top_teachers,
        "bottom_teachers": bottom_teachers,
        "risk_student_count": risk_count,
        "risk_sample": risk_sample,
        "attendance_summary": attendance_summary,
        "fee_outstanding": round(total_outstanding, 2),
        "fee_cleared_count": total_cleared,
        "fee_previous_term_outstanding": round(previous_term_outstanding, 2),
        "cbc_weakest_competencies": cbc_summary,
    }
    set_cache(cache_key, data, ttl=300)
    return data