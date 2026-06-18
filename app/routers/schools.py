from fastapi import APIRouter, status
from app.core.database import get_supabase
from app.schemas.school import (
    SchoolRegistrationRequest,
    SchoolRegistrationResponse,
)
from app.services.school_service import register_new_school

router = APIRouter(prefix="/schools", tags=["schools"])

@router.post("/register", response_model=SchoolRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_school(payload: SchoolRegistrationRequest):
    return await register_new_school(payload)

@router.get("/{school_id}/classes")
async def get_school_classes(school_id: str):
    db = get_supabase()
    return db.table("classes").select("id, name").eq("school_id", school_id).execute().data or []

@router.get("/{school_id}/teachers")
async def get_school_teachers(school_id: str):
    db = get_supabase()
    return db.table("teachers").select("id, name, teacher_code, role").eq("school_id", school_id).execute().data or []
