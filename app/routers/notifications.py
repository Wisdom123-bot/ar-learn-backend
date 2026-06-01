from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.database import get_supabase

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("/")
async def list_notifications(
    school_id: str = Query(...),
    teacher_id: Optional[str] = Query(None),
    limit: int = 20,
):
    db = get_supabase()
    query = db.table("notifications").select("*").eq("school_id", school_id).order("created_at", desc=True).limit(limit)
    if teacher_id:
        query = query.or_(f"teacher_id.eq.{teacher_id},teacher_id.is.null")
    result = query.execute()
    return result.data or []

@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str):
    db = get_supabase()
    db.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
    return {"message": "Marked as read"}