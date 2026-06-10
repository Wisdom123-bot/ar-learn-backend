from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.core.database import get_supabase
from app.services.teacher_analytics_service import compute_teacher_value_add

router = APIRouter(prefix="/analytics/teachers", tags=["teacher analytics"])

security = HTTPBearer(auto_error=False)

async def get_teacher_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    if credentials is None:
        return None
    db = get_supabase()
    teacher = db.table("teachers").select("*").eq("id", credentials.credentials).single().execute()
    if not teacher.data:
        return None
    return teacher.data


@router.get("/")
async def teacher_performance(
    school_id: str = Query(..., description="School UUID"),
    term: str = Query(..., description="Current term, e.g. 'Term 1 2025'"),
    previous_term: Optional[str] = Query(None, description="Previous term for trend, e.g. 'Term 3 2024'"),
    teacher_id: Optional[str] = Query(None, description="Optional teacher ID filter"),
    current_user: Optional[dict] = Depends(get_teacher_from_token)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    if current_user["school_id"] != school_id:
        raise HTTPException(status_code=403, detail="Access denied: wrong school")

    db = get_supabase()
    # Verify school exists
    school = db.table("schools").select("id").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    results = compute_teacher_value_add(school_id, term, previous_term)
    
    # Apply RBAC filtering
    is_admin = current_user["role"] in ("headteacher", "dean")
    
    if is_admin:
        # Admins can see everyone or filter by teacher_id
        if teacher_id:
            results = [r for r in results if r["teacher_id"] == teacher_id]
    else:
        # Regular teachers can ONLY see their own data
        # Even if they try to pass a different teacher_id, we override it
        results = [r for r in results if r["teacher_id"] == current_user["id"]]

    return {
        "term": term,
        "previous_term": previous_term,
        "teacher_count": len(results),
        "teachers": results,
    }
