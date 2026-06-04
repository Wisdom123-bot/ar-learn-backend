import random
import string
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional
from app.core.database import get_supabase

router = APIRouter(prefix="/admissions", tags=["admissions"])

# Simple dependency to get the teacher from the Bearer token
security = HTTPBearer()

def get_current_teacher(credentials: HTTPAuthorizationCredentials = Depends(security)):
    db = get_supabase()
    # We expect the token to be the teacher's UUID (stored in localStorage as teacher_id)
    teacher_id = credentials.credentials
    teacher = db.table("teachers").select("*").eq("id", teacher_id).single().execute()
    if not teacher.data:
        raise HTTPException(status_code=401, detail="Invalid teacher")
    return teacher.data


class StudentAdmitRequest(BaseModel):
    full_name: str = Field(..., example="John Doe")
    class_id: str
    admission_number: Optional[str] = None  # optional, auto‑generated if empty


class TeacherAdmitRequest(BaseModel):
    full_name: str = Field(..., example="Alice Wambui")
    role: str = "teacher"  # can be teacher, but headteacher/dean already exist? We'll default to teacher.


def generate_access_code() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


@router.post("/student")
async def admit_student(payload: StudentAdmitRequest, teacher: dict = Depends(get_current_teacher)):
    # Only headteacher or dean can admit
    if teacher["role"] not in ("headteacher", "dean"):
        raise HTTPException(status_code=403, detail="Only headteacher or dean can admit students")

    db = get_supabase()
    school_id = teacher["school_id"]

    # Verify class belongs to school
    cls = db.table("classes").select("id").eq("id", payload.class_id).eq("school_id", school_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found in your school")

    # Generate admission number if not provided
    admission = payload.admission_number
    if not admission:
        prefix = school_id[:4].upper()
        # get current count
        count = db.table("students").select("id", count="exact").eq("school_id", school_id).execute().count or 0
        admission = f"{prefix}{count + 1:04d}"

    access_code = generate_access_code()

    data = {
        "school_id": school_id,
        "class_id": payload.class_id,
        "name": payload.full_name.strip(),
        "admission_number": admission,
        "access_code": access_code,
    }
    try:
        result = db.table("students").insert(data).execute()
        if result.data:
            return {
                "message": "Student admitted successfully",
                "student": result.data[0],
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/teacher")
async def admit_teacher(payload: TeacherAdmitRequest, teacher: dict = Depends(get_current_teacher)):
    if teacher["role"] not in ("headteacher", "dean"):
        raise HTTPException(status_code=403, detail="Only headteacher or dean can admit teachers")

    db = get_supabase()
    school_id = teacher["school_id"]

    # Generate a unique teacher code using existing logic (first 3 letters + 4 digits)
    clean = payload.full_name.replace(" ", "").upper()
    prefix = clean[:3] if len(clean) >= 3 else clean.ljust(3, "X")
    # Ensure unique code
    code = prefix + ''.join(random.choices(string.digits, k=4))
    # Very unlikely collision, but check
    existing = db.table("teachers").select("id").eq("teacher_code", code).execute()
    while existing.data:
        code = prefix + ''.join(random.choices(string.digits, k=4))
        existing = db.table("teachers").select("id").eq("teacher_code", code).execute()

    data = {
        "school_id": school_id,
        "name": payload.full_name.strip(),
        "teacher_code": code,
        "role": payload.role or "teacher",
    }
    try:
        result = db.table("teachers").insert(data).execute()
        if result.data:
            return {
                "message": "Teacher admitted successfully",
                "teacher": result.data[0],
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))