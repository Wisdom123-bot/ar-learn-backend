from fastapi import APIRouter
from app.core.database import get_supabase

router = APIRouter(prefix="/subjects", tags=["subjects"])

@router.get("/")
async def list_subjects():
    db = get_supabase()
    return db.table("subjects").select("id, name").execute().data or []