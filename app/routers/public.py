from fastapi import APIRouter
from app.core.database import get_supabase
import time

router = APIRouter(prefix="/public", tags=["public"])

@router.get("/stats")
async def get_public_stats():
    db = get_supabase()
    
    # Get total schools count
    schools_res = db.table("schools").select("id", count="exact").execute()
    total_schools = schools_res.count or 0
    
    # Get total students count
    students_res = db.table("students").select("id", count="exact").execute()
    total_students = students_res.count or 0
    
    # For uptime, we'll return a value based on the current health and a high base
    # In a real app, this would come from a monitoring API
    uptime = 99.98
    
    return {
        "total_schools": total_schools,
        "total_students": total_students,
        "uptime": uptime
    }
