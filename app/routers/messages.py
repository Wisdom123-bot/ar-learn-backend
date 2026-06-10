from fastapi import APIRouter, HTTPException
from typing import List
from app.core.database import get_supabase
from app.schemas.messages import MessageCreate, MessageResponse

router = APIRouter(prefix="/messages", tags=["messages"])

@router.post("/", response_model=MessageResponse)
async def send_message(msg: MessageCreate):
    db = get_supabase()
    result = db.table("messages").insert({
        "sender_id": msg.sender_id,
        "receiver_id": msg.receiver_id,
        "student_id": msg.student_id,
        "content": msg.content
    }).execute()
    
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to send message.")
    
    return result.data[0]

@router.get("/conversation/{student_id}")
async def get_conversation(student_id: str, user1: str, user2: str):
    db = get_supabase()
    # Fetch messages between two users regarding a specific student
    result = db.table("messages")\
        .select("*")\
        .eq("student_id", student_id)\
        .or_(f"and(sender_id.eq.{user1},receiver_id.eq.{user2}),and(sender_id.eq.{user2},receiver_id.eq.{user1})")\
        .order("created_at")\
        .execute()
    
    return result.data or []

@router.get("/unread/{user_id}")
async def get_unread_count(user_id: str):
    db = get_supabase()
    result = db.table("messages")\
        .select("id", count="exact")\
        .eq("receiver_id", user_id)\
        .eq("is_read", False)\
        .execute()
    
    return {"unread_count": result.count}

@router.put("/read-all/{student_id}")
async def mark_as_read(student_id: str, receiver_id: str, sender_id: str):
    db = get_supabase()
    db.table("messages")\
        .update({"is_read": True})\
        .eq("student_id", student_id)\
        .eq("receiver_id", receiver_id)\
        .eq("sender_id", sender_id)\
        .execute()
    
    return {"message": "Messages marked as read"}
