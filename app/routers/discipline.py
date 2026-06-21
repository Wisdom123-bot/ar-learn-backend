from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import date
from app.core.database import get_supabase
from app.dependencies import get_current_user
from app.utils.security import sanitize_string, validate_uuid

router = APIRouter(prefix="/discipline", tags=["discipline"])


class DisciplineEntry(BaseModel):
    student_id: UUID
    class_id: UUID
    teacher_id: UUID
    incident_date: date
    category: str = Field(..., pattern="^(Minor|Major|Positive)$")          # Minor, Major, Positive
    description: str = Field(..., min_length=5, max_length=500)
    action_taken: str = Field("", max_length=200)


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
async def add_discipline_record(
    payload: DisciplineEntry,
    current_user: dict = Depends(get_current_user)
):
    """
    Records a disciplinary incident.
    Secure: Verifies student/teacher/class belong to the same school.
    """
    db = get_supabase()
    
    # 1. Verification of the recording teacher
    if str(payload.teacher_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot record discipline as another user.")
        
    # 2. Verification of student and school context
    student = db.table("students").select("school_id").eq("id", str(payload.student_id)).single().execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found.")
        
    if student.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied: Student belongs to another school.")

    # 3. Verification of class ownership
    cls = db.table("classes").select("school_id").eq("id", str(payload.class_id)).single().execute()
    if not cls.data or cls.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied: Class context is invalid.")

    data = {
        "student_id": validate_uuid(payload.student_id),
        "class_id": validate_uuid(payload.class_id),
        "teacher_id": validate_uuid(payload.teacher_id),
        "incident_date": payload.incident_date.isoformat(),
        "category": payload.category,
        "description": sanitize_string(payload.description, 500),
        "action_taken": sanitize_string(payload.action_taken, 200),
    }
    
    try:
        result = db.table("discipline_records").insert(data).execute()
        if result.data:
            return {"message": "Incident record archived successfully", "id": result.data[0]["id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database failure: {str(e)}")
        
    raise HTTPException(status_code=500, detail="Failed to record discipline incident.")


@router.get("/class/{class_id}", response_model=List[DisciplineResponse])
async def class_discipline_records(
    class_id: str,
    current_user: dict = Depends(get_current_user)
):
    validate_uuid(class_id)
    db = get_supabase()
    
    # Verify class belongs to school
    cls = db.table("classes").select("school_id").eq("id", class_id).single().execute()
    if not cls.data or cls.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

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
async def student_discipline_records(
    student_id: str,
    current_user: dict = Depends(get_current_user)
):
    validate_uuid(student_id)
    db = get_supabase()
    
    # Verify student belongs to school
    student = db.table("students").select("school_id").eq("id", student_id).single().execute()
    if not student.data or student.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

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
