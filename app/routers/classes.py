from fastapi import APIRouter, HTTPException
from app.core.database import get_supabase

router = APIRouter(prefix="/classes", tags=["classes"])


@router.get("/{class_id}/students")
async def get_class_students(class_id: str):
    db = get_supabase()
    # Verify class exists
    cls = db.table("classes").select("id").eq("id", class_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")
    students = (
        db.table("students")
        .select("id, name, admission_number")
        .eq("class_id", class_id)
        .order("name")
        .execute()
        .data or []
    )
    return students