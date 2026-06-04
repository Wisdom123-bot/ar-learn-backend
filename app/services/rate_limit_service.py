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
    # Fetch ALL login_attempts rows and filter in Python
    # avoids supabase-py filter syntax issues with NULL checks
    result = db.table("login_attempts").select("*").execute()
    now = datetime.now(timezone.utc)
    banned = []
    for row in (result.data or []):
        banned_until_str = row.get("banned_until")
        if not banned_until_str:
            continue
        try:
            banned_until = datetime.fromisoformat(banned_until_str)
            if banned_until > now:
                banned.append(row)
        except (ValueError, TypeError):
            continue
    return banned