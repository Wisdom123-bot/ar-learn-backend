from app.core.database import get_supabase
from typing import Optional

async def create_notification(
    school_id: str,
    title: str,
    message: str,
    category: str = "general",
    teacher_id: Optional[str] = None,
):
    """Insert a notification into the database asynchronously."""
    db = get_supabase()
    data = {
        "school_id": school_id,
        "title": title,
        "message": message,
        "category": category,
        "teacher_id": teacher_id,
    }
    try:
        # Note: This is still a synchronous call to Supabase, 
        # but we call it via BackgroundTasks to prevent blocking.
        db.table("notifications").insert(data).execute()
    except Exception:
        pass  # silent – notifications should never break the main flow
