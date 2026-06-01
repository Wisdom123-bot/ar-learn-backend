from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from uuid import UUID
from typing import Optional, List
from app.core.database import get_supabase
from collections import defaultdict

router = APIRouter(prefix="/class-teacher", tags=["class-teacher"])


class StudentResultRow(BaseModel):
    student_id: UUID
    student_name: str
    admission_number: str
    subjects: dict  # subject_name -> avg score
    overall_mean: float


class ClassTeacherDashboard(BaseModel):
    class_id: UUID
    class_name: str
    term: str
    student_results: List[StudentResultRow]
    attendance_summary: dict
    discipline_summary: dict
    top_students: List[dict]
    at_risk_students: List[dict]


class RemarkRequest(BaseModel):
    student_id: UUID
    remark: str


def get_class_teacher_class(teacher_id: str):
    db = get_supabase()
    assignment = (
        db.table("teacher_class_subjects")
        .select("class_id")
        .eq("teacher_id", teacher_id)
        .eq("is_class_teacher", True)
        .limit(1)
        .execute()
    )
    if not assignment.data:
        raise HTTPException(status_code=404, detail="No class teacher assignment found")
    class_id = assignment.data[0]["class_id"]
    cls = db.table("classes").select("id, name").eq("id", class_id).single().execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")
    return cls.data


@router.get("/dashboard", response_model=ClassTeacherDashboard)
async def class_teacher_dashboard(
    teacher_id: str = Query(..., description="Teacher ID"),
    term: str = Query("Term 1 2025"),
):
    db = get_supabase()
    cls = get_class_teacher_class(teacher_id)
    class_id = cls["id"]
    class_name = cls["name"]

    students = db.table("students").select("id, name, admission_number").eq("class_id", class_id).execute().data or []
    if not students:
        return ClassTeacherDashboard(
            class_id=class_id, class_name=class_name, term=term,
            student_results=[], attendance_summary={}, discipline_summary={},
            top_students=[], at_risk_students=[]
        )

    student_ids = [s["id"] for s in students]

    # Results
    results = db.table("results").select("student_id, subject_id, score, subjects(name)").in_("student_id", student_ids).eq("term", term).execute().data or []
    student_subject_scores = defaultdict(lambda: defaultdict(list))
    for r in results:
        subj_name = r["subjects"]["name"] if r.get("subjects") else r["subject_id"]
        student_subject_scores[r["student_id"]][subj_name].append(r["score"])

    student_results = []
    for s in students:
        subject_avgs = {}
        total_sum = 0
        total_count = 0
        for subj, scores in student_subject_scores[s["id"]].items():
            avg = sum(scores) / len(scores)
            subject_avgs[subj] = round(avg, 2)
            total_sum += sum(scores)
            total_count += len(scores)
        overall = round(total_sum / total_count, 2) if total_count > 0 else 0.0
        student_results.append(StudentResultRow(
            student_id=s["id"],
            student_name=s["name"],
            admission_number=s["admission_number"],
            subjects=subject_avgs,
            overall_mean=overall,
        ))

    # Attendance
    attendance_records = db.table("attendance").select("status").in_("student_id", student_ids).execute().data or []
    att_counts = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    for a in attendance_records:
        key = a["status"].lower()
        if key in att_counts:
            att_counts[key] += 1

    # Discipline
    discipline_records = db.table("discipline_records").select("category").eq("class_id", class_id).execute().data or []
    disc_counts = {"Minor": 0, "Major": 0, "Positive": 0}
    for d in discipline_records:
        if d["category"] in disc_counts:
            disc_counts[d["category"]] += 1

    # Top & at-risk
    top = sorted(student_results, key=lambda x: x.overall_mean, reverse=True)[:5]
    top_students = [{"name": s.student_name, "mean": s.overall_mean} for s in top]

    at_risk = [s for s in student_results if s.overall_mean < 50]
    at_risk_students = [{"name": s.student_name, "mean": s.overall_mean} for s in at_risk]

    return ClassTeacherDashboard(
        class_id=class_id, class_name=class_name, term=term,
        student_results=student_results,
        attendance_summary=att_counts,
        discipline_summary=disc_counts,
        top_students=top_students,
        at_risk_students=at_risk_students,
    )


@router.put("/remark")
async def update_class_teacher_remark(
    payload: RemarkRequest,
    teacher_id: str = Query(...),
    term: str = Query("Term 1 2025"),
):
    db = get_supabase()
    student = db.table("students").select("class_id").eq("id", str(payload.student_id)).single().execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")
    class_id = student.data["class_id"]

    assignment = (
        db.table("teacher_class_subjects")
        .select("*")
        .eq("teacher_id", teacher_id)
        .eq("class_id", class_id)
        .eq("is_class_teacher", True)
        .execute()
    )
    if not assignment.data:
        raise HTTPException(status_code=403, detail="You are not the class teacher for this student's class")

    # Upsert
    existing = db.table("class_teacher_remarks").select("id").eq("student_id", str(payload.student_id)).eq("class_id", class_id).eq("term", term).execute()
    data = {
        "student_id": str(payload.student_id),
        "class_id": class_id,
        "term": term,
        "remark": payload.remark,
        "created_by": teacher_id,
    }
    if existing.data:
        db.table("class_teacher_remarks").update(data).eq("id", existing.data[0]["id"]).execute()
    else:
        db.table("class_teacher_remarks").insert(data).execute()

    return {"message": "Remark saved"}