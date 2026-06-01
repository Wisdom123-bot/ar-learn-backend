from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.core.database import get_supabase
from app.schemas.timetable import BulkTimetableRequest, TimetableEntryResponse

router = APIRouter(prefix="/timetable", tags=["timetable"])


@router.post("/bulk")
async def create_timetable(payload: BulkTimetableRequest):
    db = get_supabase()

    # Validate school
    school = db.table("schools").select("id").eq("id", str(payload.school_id)).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    inserted = 0
    for entry in payload.entries:
        data = {
            "school_id": str(payload.school_id),
            "class_id": str(entry.class_id),
            "subject_id": str(entry.subject_id),
            "teacher_id": str(entry.teacher_id),
            "day_of_week": entry.day_of_week,
            "start_time": entry.start_time,
            "end_time": entry.end_time,
        }
        try:
            db.table("timetable_entries").insert(data).execute()
            inserted += 1
        except Exception as e:
            # Could be duplicate day+time for same class, skip
            continue

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