from datetime import datetime, timedelta, timezone
from app.core.database import get_supabase

MAX_ATTEMPTS = 5
BAN_DURATION_HOURS = 24


def is_ip_banned(ip: str) -> bool:
    db = get_supabase()
    result = db.table("login_attempts").select("banned_until").eq("ip_address", ip).execute()
    if not result.data:
        return False
    banned_until_str = result.data[0].get("banned_until")
    if not banned_until_str:
        return False
    banned_until = datetime.fromisoformat(banned_until_str)
    return banned_until > datetime.now(timezone.utc)


def record_failed_attempt(ip: str):
    db = get_supabase()
    result = db.table("login_attempts").select("*").eq("ip_address", ip).execute()
    if result.data:
        record = result.data[0]
        new_attempts = record["attempts"] + 1
        if new_attempts >= MAX_ATTEMPTS:
            banned_until = datetime.now(timezone.utc) + timedelta(hours=BAN_DURATION_HOURS)
            db.table("login_attempts").update({
                "attempts": new_attempts,
                "banned_until": banned_until.isoformat(),
                "updated_at": "now()"
            }).eq("id", record["id"]).execute()
        else:
            db.table("login_attempts").update({
                "attempts": new_attempts,
                "updated_at": "now()"
            }).eq("id", record["id"]).execute()
    else:
        db.table("login_attempts").insert({"ip_address": ip, "attempts": 1}).execute()


def reset_attempts(ip: str):
    db = get_supabase()
    db.table("login_attempts").delete().eq("ip_address", ip).execute()


def unban_ip(ip: str):
    db = get_supabase()
    db.table("login_attempts").update({
        "banned_until": None,
        "attempts": 0
    }).eq("ip_address", ip).execute()


def list_banned_ips():
    db = get_supabase()
    now = datetime.now(timezone.utc)
    # Use Supabase/PostgREST filtering to only get currently banned IPs
    result = db.table("login_attempts").select("*").gt("banned_until", now.isoformat()).execute()
    return result.data or []