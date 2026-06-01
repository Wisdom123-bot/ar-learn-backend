from fastapi import APIRouter, HTTPException
from app.core.database import get_supabase
from app.services.analytics_service import get_school_overview, get_class_analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/school/{school_id}")
async def school_dashboard(school_id: str):
    # Optional: verify school exists
    db = get_supabase()
    school = db.table("schools").select("id").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")
    return get_school_overview(school_id)


@router.get("/class/{class_id}")
async def class_dashboard(class_id: str):
    db = get_supabase()
    cls = db.table("classes").select("id").eq("id", class_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")
    return get_class_analytics(class_id)