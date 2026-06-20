from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from app.core.database import get_supabase
from app.dependencies import get_current_user
from app.services.audit_service import log_action

router = APIRouter(prefix="/subscription", tags=["subscription"])

class SubscriptionRequest(BaseModel):
    tier: str
    mpesa_message: str

@router.post("/request", status_code=status.HTTP_201_CREATED)
async def create_subscription_request(
    payload: SubscriptionRequest, 
    current_user: dict = Depends(get_current_user)
):
    if payload.tier not in ["standard", "elite"]:
        raise HTTPException(status_code=400, detail="Invalid tier selected")
    
    db = get_supabase()
    school_id = current_user["school_id"]
    
    # Get current student count for record keeping
    school = db.table("schools").select("student_count").eq("id", school_id).single().execute()
    student_count = school.data.get("student_count", 0) if school.data else 0

    data = {
        "school_id": school_id,
        "requested_tier": payload.tier,
        "mpesa_message": payload.mpesa_message,
        "student_count_at_request": student_count,
        "status": "pending"
    }
    
    result = db.table("subscription_requests").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to submit request")
    
    # Audit log
    log_action(
        school_id=school_id,
        action="SUBSCRIPTION_REQUESTED",
        actor_id=current_user["id"],
        actor_name=current_user["name"],
        entity_type="subscription",
        entity_id=result.data[0]["id"],
        new_value=data
    )
    
    return {"message": "Request submitted. Please wait up to 10 minutes for approval."}

@router.get("/status")
async def get_subscription_status(current_user: dict = Depends(get_current_user)):
    db = get_supabase()
    school_id = current_user["school_id"]
    
    school = db.table("schools").select(
        "subscription_tier, subscription_expiry, is_manual_override, student_count"
    ).eq("id", school_id).single().execute()
    
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")
    
    # Check if active
    is_active = False
    if school.data["is_manual_override"]:
        is_active = True
    elif school.data["subscription_expiry"]:
        expiry = datetime.fromisoformat(school.data["subscription_expiry"].replace('Z', '+00:00'))
        if expiry > datetime.now(expiry.tzinfo):
            is_active = True
    
    # If not active or manual override, tier is effectively 'basic' for access checks
    effective_tier = school.data["subscription_tier"] if is_active else "basic"
    
    # Check for pending requests
    pending = db.table("subscription_requests").select("*").eq("school_id", school_id).eq("status", "pending").execute()
    
    return {
        "tier": effective_tier,
        "actual_tier": school.data["subscription_tier"],
        "is_active": is_active,
        "expiry": school.data["subscription_expiry"],
        "has_pending": len(pending.data) > 0,
        "student_count": school.data["student_count"]
    }
