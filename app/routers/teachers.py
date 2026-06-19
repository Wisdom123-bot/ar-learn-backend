from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel
from app.core.database import get_supabase
from app.schemas.teacher import TeacherAssignRequest
from app.schemas.student import StudentBrief

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.put("/{teacher_id}/assign")
async def assign_teacher(teacher_id: str, payload: TeacherAssignRequest):
    db = get_supabase()

    teacher = db.table("teachers").select("*").eq("id", teacher_id).execute()
    if not teacher.data:
        raise HTTPException(status_code=404, detail="Teacher not found")

    school_id = teacher.data[0]["school_id"]

    for assignment in payload.assignments:
        cls = db.table("classes").select("id").eq("id", str(assignment.class_id)).eq("school_id", school_id).execute()
        if not cls.data:
            raise HTTPException(status_code=400, detail=f"Class {assignment.class_id} not in this school")
        subject = db.table("subjects").select("id").eq("id", str(assignment.subject_id)).execute()
        if not subject.data:
            raise HTTPException(status_code=400, detail=f"Subject {assignment.subject_id} not found")

    db.table("teacher_class_subjects").delete().eq("teacher_id", teacher_id).execute()

    # Batch insert assignments
    insert_data = [
        {
            "teacher_id": teacher_id,
            "class_id": str(assignment.class_id),
            "subject_id": str(assignment.subject_id),
            "is_class_teacher": assignment.is_class_teacher,
        }
        for assignment in payload.assignments
    ]
    if insert_data:
        db.table("teacher_class_subjects").insert(insert_data).execute()

    return {"message": f"Teacher assigned to {len(payload.assignments)} class-subject entries"}
@router.get("/{teacher_id}/profile")
async def get_teacher_profile(teacher_id: str):
    db = get_supabase()

    # 1. Teacher basic info
    teacher = db.table("teachers").select("id, name, teacher_code, role, phone, school_id").eq("id", teacher_id).single().execute()
    if not teacher.data:
        raise HTTPException(status_code=404, detail="Teacher not found")
    t = teacher.data
    school = db.table("schools").select("name").eq("id", t["school_id"]).single().execute()
    school_name = school.data["name"] if school.data else ""

    # 2. Assignments (classes & subjects) - JOINED to avoid N+1
    assignments = db.table("teacher_class_subjects").select("*, classes(name), subjects(name)").eq("teacher_id", teacher_id).execute().data or []
    enriched_assignments = [
        {
            "class_name": a["classes"]["name"] if a.get("classes") else "Unknown",
            "subject_name": a["subjects"]["name"] if a.get("subjects") else "Unknown",
            "is_class_teacher": a["is_class_teacher"],
        }
        for a in assignments
    ]

    # 3. Timetable
    timetable = db.table("timetable_entries").select("day_of_week, start_time, end_time, subjects(name)").eq("teacher_id", teacher_id).order("day_of_week, start_time").execute().data or []

    return {
        "teacher": {
            "id": t["id"],
            "name": t["name"],
            "teacher_code": t["teacher_code"],
            "role": t["role"],
            "phone": t.get("phone", ""),
            "school_name": school_name,
        },
        "assignments": enriched_assignments,
        "timetable": timetable,
    }
@router.get("/{teacher_id}/assignments")
async def get_teacher_assignments(teacher_id: str):
    db = get_supabase()
    # Join with classes and subjects in one query
    result = db.table("teacher_class_subjects").select("*, classes(name), subjects(name)").eq("teacher_id", teacher_id).execute()
    data = result.data or []
    for a in data:
        a["class_name"] = a["classes"]["name"] if a.get("classes") else "Unknown"
        a["subject_name"] = a["subjects"]["name"] if a.get("subjects") else "Unknown"
    return data


class PhoneUpdate(BaseModel):
    phone: str

@router.put("/{teacher_id}/phone")
async def update_teacher_phone(teacher_id: str, payload: PhoneUpdate):
    db = get_supabase()
    result = db.table("teachers").update({"phone": payload.phone}).eq("id", teacher_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return {"message": "Phone number updated"}

@router.get("/{teacher_id}/students", response_model=List[StudentBrief])
async def get_assigned_students(teacher_id: str):
    db = get_supabase()

    # 1. Get all class IDs this teacher is assigned to
    assignments = db.table("teacher_class_subjects").select("class_id").eq("teacher_id", teacher_id).execute()
    if not assignments.data:
        return []

    class_ids = list({a["class_id"] for a in assignments.data})

    # 2. Fetch students in those classes with class names joined (Avoiding N+1)
    result = db.table("students").select("*, classes(name)").in_("class_id", class_ids).execute()
    data = result.data or []

    return [
        StudentBrief(
            id=s["id"],
            name=s["name"],
            admission_number=s["admission_number"],
            class_id=s["class_id"],
            class_name=s["classes"]["name"] if s.get("classes") else "Unknown",
        )
        for s in data
    ]
