from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.database import get_supabase
from collections import defaultdict

router = APIRouter(prefix="/dean", tags=["dean"])


@router.get("/dashboard")
async def dean_dashboard(
    school_id: str = Query(...),
    term: str = Query("Term 1 2025"),
):
    db = get_supabase()

    # 1. School-wide attendance summary
    students = db.table("students").select("id, name, admission_number, class_id, classes(name)").eq("school_id", school_id).execute().data
    student_ids = [s["id"] for s in students] if students else []
    student_map = {s["id"]: s for s in students}

    attendance_summary = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    attendance_details = defaultdict(list)
    if student_ids:
        att_records = db.table("attendance").select("student_id, status, date").in_("student_id", student_ids).execute().data or []
        for a in att_records:
            key = a["status"].lower()
            if key in attendance_summary:
                attendance_summary[key] += 1
                s = student_map.get(a["student_id"])
                if s:
                    attendance_details[key].append({
                        "student_id": s["id"],
                        "student_name": s["name"],
                        "admission_number": s["admission_number"],
                        "class_name": s["classes"]["name"] if s.get("classes") else "N/A",
                        "status": a["status"],
                        "date": a["date"]
                    })

    # 2. School-wide discipline summary
    discipline_summary = {"Minor": 0, "Major": 0, "Positive": 0}
    discipline_details = defaultdict(list)
    classes = db.table("classes").select("id, name").eq("school_id", school_id).execute().data or []
    if classes:
        class_ids = [c["id"] for c in classes]
        disc_records = db.table("discipline_records").select("*, students(name, admission_number), classes(name)").in_("class_id", class_ids).execute().data or []
        for d in disc_records:
            cat = d["category"]
            if cat in discipline_summary:
                discipline_summary[cat] += 1
                discipline_details[cat].append({
                    "student_name": d["students"]["name"] if d.get("students") else "Unknown",
                    "admission_number": d["students"]["admission_number"] if d.get("students") else "N/A",
                    "class_name": d["classes"]["name"] if d.get("classes") else "N/A",
                    "category": cat,
                    "description": d["description"],
                    "incident_date": d["incident_date"],
                    "action_taken": d.get("action_taken", "")
                })

    # 3. Attendance concerns per class (classes with < 75% attendance rate)
    attendance_concerns = []
    for cls in classes:
        cls_students = db.table("students").select("id").eq("class_id", cls["id"]).execute().data
        cls_student_ids = [s["id"] for s in cls_students]
        total = present = 0
        if cls_student_ids:
            att = db.table("attendance").select("status").in_("student_id", cls_student_ids).execute().data or []
            for a in att:
                total += 1
                if a["status"].lower() == "present":
                    present += 1
        if total > 0:
            rate = (present / total) * 100
            if rate < 75:
                attendance_concerns.append({"class_name": cls["name"], "attendance_pct": round(rate, 1)})

    # 4. Most disciplined classes (most Positive entries per class)
    discipline_per_class = []
    for cls in classes:
        pos = db.table("discipline_records").select("id").eq("class_id", cls["id"]).eq("category", "Positive").execute().data
        discipline_per_class.append({"class_name": cls["name"], "positive_count": len(pos) if pos else 0})
    discipline_per_class.sort(key=lambda x: x["positive_count"], reverse=True)
    most_disciplined = discipline_per_class[:3]

    # 5. Risk summary – count students with overall mean < 50
    risk_count = 0
    risk_class_counts = defaultdict(int)
    for cls in classes:
        cls_students = db.table("students").select("id").eq("class_id", cls["id"]).execute().data
        cls_sids = [s["id"] for s in cls_students]
        if not cls_sids:
            continue
        results = db.table("results").select("student_id, score").in_("student_id", cls_sids).eq("term", term).execute().data or []
        student_scores = defaultdict(list)
        for r in results:
            student_scores[r["student_id"]].append(r["score"])
        for sid, scores in student_scores.items():
            if sum(scores) / len(scores) < 50:
                risk_count += 1
                risk_class_counts[cls["name"]] += 1

    return {
        "attendance_summary": attendance_summary,
        "attendance_details": dict(attendance_details),
        "discipline_summary": discipline_summary,
        "discipline_details": dict(discipline_details),
        "attendance_concerns": attendance_concerns,
        "most_disciplined_classes": most_disciplined,
        "risk_student_count": risk_count,
        "risk_by_class": dict(risk_class_counts),
    }
