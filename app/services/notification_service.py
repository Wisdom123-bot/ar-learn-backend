from app.core.database import get_supabase
from typing import Optional

def create_notification(
    school_id: str,
    title: str,
    message: str,
    category: str = "general",
    teacher_id: Optional[str] = None,
):
    """Insert a notification into the database."""
    db = get_supabase()
    data = {
        "school_id": school_id,
        "title": title,
        "message": message,
        "category": category,
        "teacher_id": teacher_id,
    }
    try:
        db.table("notifications").insert(data).execute()
    except Exception:
        pass  # silent – notifications should never break the main flow