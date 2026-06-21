from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, Field
from typing import Optional
from app.core.database import get_supabase
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.services.rate_limit_service import is_ip_banned, record_failed_attempt, reset_attempts
from app.utils.security import sanitize_search_query

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- Schemas ----------
class TeacherLoginRequest(BaseModel):
    teacher_code: str = Field(..., min_length=4, max_length=15, pattern=r"^[A-Z0-9]+$")


class TeacherLoginResponse(BaseModel):
    token: str
    refresh_token: str
    teacher_id: str
    name: str
    teacher_code: str
    school_id: str
    school_name: str
    role: str = "teacher"
    is_premium: bool = False
    subscription_tier: str = "basic"
    slug: Optional[str] = None
    logo_url: Optional[str] = None


class SchoolSearchResult(BaseModel):
    id: str
    name: str
    county: str


class UnifiedLoginRequest(BaseModel):
    school_id: str = Field(..., pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    role: str = Field(..., pattern="^(headteacher|dean|teacher)$")
    teacher_code: str = Field(..., min_length=4, max_length=15, pattern=r"^[A-Z0-9]+$")


class UnifiedLoginResponse(BaseModel):
    token: str
    refresh_token: str
    teacher_id: str
    name: str
    teacher_code: str
    school_id: str
    school_name: str
    role: str
    is_premium: bool = False
    subscription_tier: str = "basic"
    slug: Optional[str] = None
    logo_url: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh")
async def refresh_token(payload: RefreshRequest):
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = decoded.get("sub")
    role = decoded.get("role")
    
    new_access_token = create_access_token(data={"sub": user_id, "role": role})
    return {"token": new_access_token}


def get_client_ip(request: Request) -> str:
    """Extract real client IP from Render's x-forwarded-for header."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


# ---------- Legacy Teacher Login ----------
@router.post("/teacher/login", response_model=TeacherLoginResponse)
async def teacher_login(payload: TeacherLoginRequest, request: Request):
    ip = get_client_ip(request)
    if is_ip_banned(ip):
        raise HTTPException(status_code=403, detail="Too many failed attempts. Please try again later.")

    db = get_supabase()

    result = (
        db.table("teachers")
        .select("*, schools(name, is_active, is_premium, subscription_tier, subscription_expiry, is_manual_override, slug, logo_url)")
        .eq("teacher_code", payload.teacher_code)
        .execute()
    )

    if not result.data:
        record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail="Invalid teacher code.")

    teacher = result.data[0]
    school_data = teacher.get("schools")

    if school_data and not school_data.get("is_active", True):
        raise HTTPException(status_code=403, detail="School account is suspended.")

    # Calculate tier
    is_active_sub = False
    if school_data.get("is_manual_override"):
        is_active_sub = True
    elif school_data.get("subscription_expiry"):
        import datetime
        try:
            expiry = datetime.datetime.fromisoformat(school_data["subscription_expiry"].replace('Z', '+00:00'))
            if expiry > datetime.datetime.now(expiry.tzinfo):
                is_active_sub = True
        except:
            pass
    
    tier = school_data.get("subscription_tier", "basic") if is_active_sub else "basic"
    if school_data.get("is_premium") and tier == "basic":
        tier = "standard"

    reset_attempts(ip)
    
    # Generate JWT tokens
    access_token = create_access_token(data={"sub": teacher["id"], "role": teacher.get("role", "teacher")})
    refresh_token = create_refresh_token(data={"sub": teacher["id"], "role": teacher.get("role", "teacher")})

    return TeacherLoginResponse(
        token=access_token,
        refresh_token=refresh_token,
        teacher_id=teacher["id"],
        name=teacher["name"],
        teacher_code=teacher["teacher_code"],
        school_id=teacher["school_id"],
        school_name=school_data["name"] if school_data else "",
        role=teacher.get("role", "teacher"),
        is_premium=school_data.get("is_premium", False) if school_data else False,
        subscription_tier=tier,
        slug=school_data.get("slug") if school_data else None,
        logo_url=school_data.get("logo_url") if school_data else None,
    )


# ---------- School Search ----------
@router.get("/schools/search", response_model=list[SchoolSearchResult])
async def search_schools(name: str):
    safe_name = sanitize_search_query(name)
    if not safe_name or len(safe_name) < 2:
        raise HTTPException(status_code=400, detail="Search term too short")
    db = get_supabase()
    result = (
        db.table("schools")
        .select("id, name, county")
        .ilike("name", f"%{safe_name}%")
        .execute()
    )
    return [
        SchoolSearchResult(id=s["id"], name=s["name"], county=s["county"])
        for s in (result.data or [])
    ]


# ---------- Unified Role‑Based Login ----------
@router.post("/login", response_model=UnifiedLoginResponse)
async def unified_login(payload: UnifiedLoginRequest, request: Request):
    ip = get_client_ip(request)
    if is_ip_banned(ip):
        raise HTTPException(status_code=403, detail="Too many failed attempts. Please try again later.")

    db = get_supabase()

    # 1. Validate school
    school = (
        db.table("schools")
        .select("id, name, is_active, is_premium, subscription_tier, subscription_expiry, is_manual_override, slug, logo_url")
        .eq("id", payload.school_id)
        .single()
        .execute()
    )
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")
    if not school.data["is_active"]:
        raise HTTPException(status_code=403, detail="School account is suspended.")

    # Calculate tier
    is_active_sub = False
    if school.data.get("is_manual_override"):
        is_active_sub = True
    elif school.data.get("subscription_expiry"):
        import datetime
        try:
            expiry = datetime.datetime.fromisoformat(school.data["subscription_expiry"].replace('Z', '+00:00'))
            if expiry > datetime.datetime.now(expiry.tzinfo):
                is_active_sub = True
        except:
            pass
    
    tier = school.data.get("subscription_tier", "basic") if is_active_sub else "basic"
    if school.data.get("is_premium") and tier == "basic":
        tier = "standard"

    # 2. Validate role
    if payload.role not in ("headteacher", "dean", "teacher"):
        raise HTTPException(status_code=400, detail="Invalid role")

    # 3. Find teacher with the given code, school, and role
    result = (
        db.table("teachers")
        .select("*")
        .eq("teacher_code", payload.teacher_code)
        .eq("school_id", payload.school_id)
        .eq("role", payload.role)
        .execute()
    )

    if not result.data:
        record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials for the selected role.")

    teacher = result.data[0]
    reset_attempts(ip)

    # Generate JWT tokens
    access_token = create_access_token(data={"sub": teacher["id"], "role": teacher["role"]})
    refresh_token = create_refresh_token(data={"sub": teacher["id"], "role": teacher["role"]})

    return UnifiedLoginResponse(
        token=access_token,
        refresh_token=refresh_token,
        teacher_id=teacher["id"],
        name=teacher["name"],
        teacher_code=teacher["teacher_code"],
        school_id=teacher["school_id"],
        school_name=school.data["name"],
        role=teacher["role"],
        is_premium=school.data.get("is_premium", False),
        subscription_tier=tier,
        slug=school.data.get("slug"),
        logo_url=school.data.get("logo_url"),
    )