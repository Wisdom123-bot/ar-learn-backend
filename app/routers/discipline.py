from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel
from uuid import UUID
from datetime import date
from app.core.database import get_supabase

router = APIRouter(prefix="/discipline", tags=["discipline"])


class DisciplineEntry(BaseModel):
    student_id: UUID
    class_id: UUID
    teacher_id: UUID
    incident_date: date
    category: str          # Minor, Major, Positive
    description: str
    action_taken: str = ""


class DisciplineResponse(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str = ""
    class_id: UUID
    class_name: str = ""
    teacher_name: str = ""
    incident_date: date
    category: str
    description: str
    action_taken: str
    created_at: str


@router.post("/record")
async def add_discipline_record(payload: DisciplineEntry):
    db = get_supabase()
    data = {
        "student_id": str(payload.student_id),
        "class_id": str(payload.class_id),
        "teacher_id": str(payload.teacher_id),
        "incident_date": payload.incident_date.isoformat(),
        "category": payload.category,
        "description": payload.description,
        "action_taken": payload.action_taken,
    }
    result = db.table("discipline_records").insert(data).execute()
    if result.data:
        return {"message": "Discipline record added", "id": result.data[0]["id"]}
    raise HTTPException(status_code=500, detail="Failed to record discipline")


@router.get("/class/{class_id}", response_model=List[DisciplineResponse])
async def class_discipline_records(class_id: str):
    db = get_supabase()
    records = (
        db.table("discipline_records")
        .select("*, students(name), classes(name), teachers(name)")
        .eq("class_id", class_id)
        .order("incident_date", desc=True)
        .execute()
        .data or []
    )
    return [
        DisciplineResponse(
            id=r["id"],
            student_id=r["student_id"],
            student_name=r["students"]["name"] if r.get("students") else "",
            class_id=r["class_id"],
            class_name=r["classes"]["name"] if r.get("classes") else "",
            teacher_name=r["teachers"]["name"] if r.get("teachers") else "",
            incident_date=r["incident_date"],
            category=r["category"],
            description=r["description"],
            action_taken=r.get("action_taken", ""),
            created_at=str(r["created_at"]),
        )
        for r in records
    ]


@router.get("/student/{student_id}", response_model=List[DisciplineResponse])
async def student_discipline_records(student_id: str):
    db = get_supabase()
    records = (
        db.table("discipline_records")
        .select("*, students(name), classes(name), teachers(name)")
        .eq("student_id", student_id)
        .order("incident_date", desc=True)
        .execute()
        .data or []
    )
    return [
        DisciplineResponse(
            id=r["id"],
            student_id=r["student_id"],
            student_name=r["students"]["name"] if r.get("students") else "",
            class_id=r["class_id"],
            class_name=r["classes"]["name"] if r.get("classes") else "",
            teacher_name=r["teachers"]["name"] if r.get("teachers") else "",
            incident_date=r["incident_date"],
            category=r["category"],
            description=r["description"],
            action_taken=r.get("action_taken", ""),
            created_at=str(r["created_at"]),
        )
        for r in records
    ]