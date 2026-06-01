from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.database import get_supabase
from app.services.headteacher_dashboard_service import get_headteacher_dashboard

router = APIRouter(prefix="/headteacher", tags=["headteacher"])


@router.get("/dashboard")
async def headteacher_dashboard(
    school_id: str = Query(..., description="School UUID"),
    term: str = Query(..., description="Current term, e.g. 'Term 1 2025'"),
    previous_term: Optional[str] = Query(None, description="Previous term for comparison"),
):
    db = get_supabase()
    # Verify school exists
    school = db.table("schools").select("id").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    data = get_headteacher_dashboard(school_id, term, previous_term)
    return data