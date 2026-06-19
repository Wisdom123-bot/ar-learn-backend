from fastapi import APIRouter, HTTPException, Query, Response
from typing import List, Optional
from app.core.database import get_supabase
from app.schemas.timetable import BulkTimetableRequest, TimetableEntryResponse
from app.services.timetable_pdf_service import generate_timetable_pdf

router = APIRouter(prefix="/timetable", tags=["timetable"])


@router.post("/bulk")
async def create_timetable(payload: BulkTimetableRequest):
    db = get_supabase()

    # Validate school
    school = db.table("schools").select("id").eq("id", str(payload.school_id)).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    inserted = 0
    entries_to_insert = []
    for entry in payload.entries:
        entries_to_insert.append({
            "school_id": str(payload.school_id),
            "class_id": str(entry.class_id),
            "subject_id": str(entry.subject_id),
            "teacher_id": str(entry.teacher_id),
            "day_of_week": entry.day_of_week,
            "start_time": entry.start_time,
            "end_time": entry.end_time,
        })

    if entries_to_insert:
        try:
            result = db.table("timetable_entries").insert(entries_to_insert).execute()
            inserted = len(result.data) if result.data else 0
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to insert timetable entries: {str(e)}")

    return {"message": f"{inserted} timetable entries created", "count": inserted}


@router.get("/class/{class_id}", response_model=List[TimetableEntryResponse])
async def get_class_timetable(class_id: str):
    db = get_supabase()

    cls = db.table("classes").select("id").eq("id", class_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")

    entries = (
        db.table("timetable_entries")
        .select("*, classes(name), subjects(name), teachers(name)")
        .eq("class_id", class_id)
        .order("day_of_week, start_time")
        .execute()
        .data or []
    )

    result = []
    for e in entries:
        result.append(TimetableEntryResponse(
            id=e["id"],
            class_id=e["class_id"],
            class_name=e["classes"]["name"] if e.get("classes") else "",
            subject_id=e["subject_id"],
            subject_name=e["subjects"]["name"] if e.get("subjects") else "",
            teacher_id=e["teacher_id"],
            teacher_name=e["teachers"]["name"] if e.get("teachers") else "",
            day_of_week=e["day_of_week"],
            start_time=e["start_time"],
            end_time=e["end_time"],
            created_at=str(e["created_at"]),
        ))
    return result


@router.delete("/{entry_id}")
async def delete_timetable_entry(entry_id: str):
    db = get_supabase()
    db.table("timetable_entries").delete().eq("id", entry_id).execute()
    return {"message": "Deleted"}


@router.get("/teacher/{teacher_id}", response_model=List[TimetableEntryResponse])
async def get_teacher_timetable(teacher_id: str):
    db = get_supabase()
    entries = (
        db.table("timetable_entries")
        .select("*, classes(name), subjects(name), teachers(name)")
        .eq("teacher_id", teacher_id)
        .order("day_of_week, start_time")
        .execute()
        .data or []
    )
    result = []
    for e in entries:
        result.append(TimetableEntryResponse(
            id=e["id"],
            class_id=e["class_id"],
            class_name=e["classes"]["name"] if e.get("classes") else "",
            subject_id=e["subject_id"],
            subject_name=e["subjects"]["name"] if e.get("subjects") else "",
            teacher_id=e["teacher_id"],
            teacher_name=e["teachers"]["name"] if e.get("teachers") else "",
            day_of_week=e["day_of_week"],
            start_time=e["start_time"],
            end_time=e["end_time"],
            created_at=str(e["created_at"]),
        ))
    return result


@router.get("/pdf/class/{class_id}")
async def download_class_timetable_pdf(class_id: str):
    db = get_supabase()
    cls = db.table("classes").select("name, school_id, schools(name)").eq("id", class_id).single().execute().data
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    
    entries = (
        db.table("timetable_entries")
        .select("*, subjects(name), teachers(name)")
        .eq("class_id", class_id)
        .execute()
        .data or []
    )
    
    school_name = cls["schools"]["name"] if cls.get("schools") else "Ar-Learn School"
    pdf_bytes = generate_timetable_pdf(entries, f"Class Timetable: {cls['name']}", school_name)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=timetable_class_{class_id}.pdf"}
    )


@router.get("/pdf/teacher/{teacher_id}")
async def download_teacher_timetable_pdf(teacher_id: str):
    db = get_supabase()
    teacher = db.table("teachers").select("name, school_id, schools(name)").eq("id", teacher_id).single().execute().data
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    entries = (
        db.table("timetable_entries")
        .select("*, subjects(name), classes(name)")
        .eq("teacher_id", teacher_id)
        .execute()
        .data or []
    )
    
    school_name = teacher["schools"]["name"] if teacher.get("schools") else "Ar-Learn School"
    pdf_bytes = generate_timetable_pdf(entries, f"Teacher Timetable: {teacher['name']}", school_name)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=timetable_teacher_{teacher_id}.pdf"}
    )
