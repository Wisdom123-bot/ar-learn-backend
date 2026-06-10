from fastapi import APIRouter, Query, HTTPException, status
from typing import Optional, List
from pydantic import BaseModel
from app.core.database import get_supabase
from uuid import UUID

router = APIRouter(prefix="/subjects", tags=["subjects"])

class SubjectCreate(BaseModel):
    name: str
    school_id: UUID

class SubjectUpdate(BaseModel):
    name: str

@router.get("/")
async def list_subjects(school_id: Optional[str] = Query(None)):
    db = get_supabase()
    query = db.table("subjects").select("id, name, school_id")
    if school_id:
        query = query.eq("school_id", school_id)
    
    return query.execute().data or []

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_subject(payload: SubjectCreate):
    db = get_supabase()
    
    # Check if subject already exists for this school
    existing = db.table("subjects").select("id").eq("school_id", str(payload.school_id)).eq("name", payload.name.strip()).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Subject already exists for this school")

    result = db.table("subjects").insert({
        "name": payload.name.strip(),
        "school_id": str(payload.school_id)
    }).execute()
    
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create subject")
    return result.data[0]

@router.put("/{subject_id}")
async def update_subject(subject_id: str, payload: SubjectUpdate):
    db = get_supabase()
    result = db.table("subjects").update({"name": payload.name.strip()}).eq("id", subject_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Subject not found")
    return result.data[0]

@router.delete("/{subject_id}")
async def delete_subject(subject_id: str):
    db = get_supabase()
    
    # Check for dependencies (results or assignments)
    # 1. Check results
    results = db.table("results").select("id").eq("subject_id", subject_id).limit(1).execute()
    if results.data:
        raise HTTPException(status_code=400, detail="Cannot delete subject with existing results. Remove results first.")
    
    # 2. Check assignments
    assignments = db.table("teacher_class_subjects").select("teacher_id").eq("subject_id", subject_id).limit(1).execute()
    if assignments.data:
        raise HTTPException(status_code=400, detail="Cannot delete subject assigned to teachers. Remove assignments first.")

    db.table("subjects").delete().eq("id", subject_id).execute()
    return {"message": "Subject deleted successfully"}
