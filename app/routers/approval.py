from fastapi import APIRouter, HTTPException, status
from app.core.database import get_supabase
from app.schemas.approval import ApprovalRequest

router = APIRouter(prefix="/approval", tags=["approval"])


@router.post("/review")
async def review_results(payload: ApprovalRequest):
    db = get_supabase()

    # 1. Verify headteacher exists and belongs to the same school as the class
    ht = db.table("teachers").select("id, school_id").eq("id", str(payload.headteacher_id)).execute()
    if not ht.data:
        raise HTTPException(status_code=404, detail="Headteacher not found")

    cls = db.table("classes").select("id, school_id").eq("id", str(payload.class_id)).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")

    if ht.data[0]["school_id"] != cls.data[0]["school_id"]:
        raise HTTPException(status_code=403, detail="Headteacher does not belong to this school")

    # 2. Update all results for this class and term that are still pending
    update_data = {
        "approval_status": payload.action + "d",  # "approved" or "rejected"
        "approved_by": str(payload.headteacher_id),
        "approval_remarks": payload.remarks or "",
    }

    result = (
        db.table("results")
        .update(update_data)
        .eq("class_id", str(payload.class_id))
        .eq("term", payload.term)
        .eq("approval_status", "pending")
        .execute()
    )

    # Supabase returns updated rows? It returns the new data.
    count = len(result.data) if result.data else 0
    return {"message": f"Results {payload.action}d", "updated_count": count}