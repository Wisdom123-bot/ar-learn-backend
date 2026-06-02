from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_supabase

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- Schemas ----------
class TeacherLoginRequest(BaseModel):
    teacher_code: str


class TeacherLoginResponse(BaseModel):
    teacher_id: str
    name: str
    teacher_code: str
    school_id: str
    school_name: str
    role: str = "teacher"
    is_premium: bool = False
    slug: Optional[str] = None
    logo_url: Optional[str] = None


class SchoolSearchResult(BaseModel):
    id: str
    name: str
    county: str


class UnifiedLoginRequest(BaseModel):
    school_id: str
    role: str          # headteacher, dean, teacher
    teacher_code: str


class UnifiedLoginResponse(BaseModel):
    teacher_id: str
    name: str
    teacher_code: str
    school_id: str
    school_name: str
    role: str
    is_premium: bool = False
    slug: Optional[str] = None
    logo_url: Optional[str] = None


# ---------- Legacy Teacher Login ----------
@router.post("/teacher/login", response_model=TeacherLoginResponse)
async def teacher_login(payload: TeacherLoginRequest):
    db = get_supabase()

    result = (
        db.table("teachers")
        .select("*, schools(name, is_active, is_premium, slug, logo_url)")
        .eq("teacher_code", payload.teacher_code)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid teacher code.")

    teacher = result.data[0]
    school_data = teacher.get("schools")

    if school_data and not school_data.get("is_active", True):
        raise HTTPException(status_code=403, detail="School account is suspended.")

    return TeacherLoginResponse(
        teacher_id=teacher["id"],
        name=teacher["name"],
        teacher_code=teacher["teacher_code"],
        school_id=teacher["school_id"],
        school_name=school_data["name"] if school_data else "",
        role=teacher.get("role", "teacher"),
        is_premium=school_data.get("is_premium", False) if school_data else False,
        slug=school_data.get("slug") if school_data else None,
        logo_url=school_data.get("logo_url") if school_data else None,
    )


# ---------- School Search ----------
@router.get("/schools/search", response_model=list[SchoolSearchResult])
async def search_schools(name: str):
    if not name or len(name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Search term too short")
    db = get_supabase()
    result = (
        db.table("schools")
        .select("id, name, county")
        .ilike("name", f"%{name.strip()}%")
        .execute()
    )
    return [
        SchoolSearchResult(id=s["id"], name=s["name"], county=s["county"])
        for s in (result.data or [])
    ]


# ---------- Unified Role‑Based Login ----------
@router.post("/login", response_model=UnifiedLoginResponse)
async def unified_login(payload: UnifiedLoginRequest):
    db = get_supabase()

    # 1. Validate school
    school = (
        db.table("schools")
        .select("id, name, is_active, is_premium, slug, logo_url")
        .eq("id", payload.school_id)
        .single()
        .execute()
    )
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")
    if not school.data["is_active"]:
        raise HTTPException(status_code=403, detail="School account is suspended.")

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
        raise HTTPException(status_code=401, detail="Invalid credentials for the selected role.")

    teacher = result.data[0]

    return UnifiedLoginResponse(
        teacher_id=teacher["id"],
        name=teacher["name"],
        teacher_code=teacher["teacher_code"],
        school_id=teacher["school_id"],
        school_name=school.data["name"],
        role=teacher["role"],
        is_premium=school.data.get("is_premium", False),
        slug=school.data.get("slug"),
        logo_url=school.data.get("logo_url"),
    )