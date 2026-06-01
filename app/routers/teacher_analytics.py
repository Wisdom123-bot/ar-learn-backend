from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.database import get_supabase
from app.services.teacher_analytics_service import compute_teacher_value_add

router = APIRouter(prefix="/analytics/teachers", tags=["teacher analytics"])


@router.get("/")
async def teacher_performance(
    school_id: str = Query(..., description="School UUID"),
    term: str = Query(..., description="Current term, e.g. 'Term 1 2025'"),
    previous_term: Optional[str] = Query(None, description="Previous term for trend, e.g. 'Term 3 2024'"),
):
    db = get_supabase()
    # Verify school exists
    school = db.table("schools").select("id").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    results = compute_teacher_value_add(school_id, term, previous_term)
    return {
        "term": term,
        "previous_term": previous_term,
        "teacher_count": len(results),
        "teachers": results,
    }