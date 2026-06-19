from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.core.database import get_supabase
from app.schemas.badges import Badge, StudentBadgeAward, StudentBadgeResponse

router = APIRouter(prefix="/badges", tags=["badges"])

@router.get("", response_model=List[Badge])
async def get_all_badges():
    db = get_supabase()
    result = db.table("badges").select("*").execute()
    return result.data or []

@router.post("/award")
async def award_badge(award: StudentBadgeAward):
    db = get_supabase()
    
    # Check if already awarded for this term
    existing = db.table("student_badges").select("*")\
        .eq("student_id", award.student_id)\
        .eq("badge_id", award.badge_id)\
        .eq("term", award.term)\
        .execute()
    
    if existing.data:
        raise HTTPException(status_code=400, detail="Badge already awarded to this student for this term.")
    
    result = db.table("student_badges").insert({
        "student_id": award.student_id,
        "badge_id": award.badge_id,
        "awarded_by": award.awarded_by,
        "term": award.term
    }).execute()
    
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to award badge.")
    
    return {"message": "Badge awarded successfully", "data": result.data[0]}

@router.get("/student/{student_id}", response_model=List[StudentBadgeResponse])
async def get_student_badges(student_id: str):
    db = get_supabase()
    # Join with badges and teachers
    result = db.table("student_badges")\
        .select("*, badges(*), teachers(name)")\
        .eq("student_id", student_id)\
        .execute()
    
    output = []
    for item in (result.data or []):
        output.append({
            "id": item["id"],
            "student_id": item["student_id"],
            "badge": item["badges"],
            "awarded_by_name": item["teachers"]["name"] if item.get("teachers") else "Unknown",
            "awarded_at": item["awarded_at"],
            "term": item["term"]
        })
    return output
