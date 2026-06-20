import random
import string
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from app.core.database import get_supabase
from app.dependencies import get_current_user
from app.services.audit_service import log_action

router = APIRouter(prefix="/admissions", tags=["admissions"])


class StudentAdmitRequest(BaseModel):
    full_name: str = Field(..., example="John Doe")
    class_id: str
    admission_number: Optional[str] = None  # optional, auto‑generated if empty


class TeacherAdmitRequest(BaseModel):
    full_name: str = Field(..., example="Alice Wambui")
    role: str = "teacher"


def generate_access_code() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def check_admin_auth(teacher: dict):
    if teacher["role"] not in ("headteacher", "dean"):
        raise HTTPException(status_code=403, detail="Access denied: Admin permissions required for admissions.")


@router.post("/student")
async def admit_student(
    payload: StudentAdmitRequest, 
    current_user: dict = Depends(get_current_user)
):
    """
    Admits a student to a class.
    Secure: Scopes admission numbers and class verification to current school.
    """
    check_admin_auth(current_user)
    db = get_supabase()
    school_id = current_user["school_id"]

    # 1. Verify class exists and belongs to the school
    cls = db.table("classes").select("id").eq("id", payload.class_id).eq("school_id", school_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Target class not found in your school records.")

    # 2. Sequential Admission Number Logic
    admission = payload.admission_number
    if not admission:
        prefix = school_id[:4].upper()
        # Strictly count students WITHIN the school to prevent global leak
        count_res = db.table("students").select("id", count="exact").eq("school_id", school_id).execute()
        count = count_res.count or 0
        admission = f"{prefix}{count + 1:04d}"

    # 3. Security Code Generation
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
            # Audit log
            log_action(
                school_id=school_id,
                action="STUDENT_ADMITTED",
                actor_id=current_user["id"],
                actor_name=current_user["name"],
                entity_type="student",
                entity_id=result.data[0]["id"],
                new_value=data
            )
            
            # Increment school student count
            db.rpc("increment_student_count", {"p_school_id": school_id}).execute()

            return {
                "message": f"Student {payload.full_name} admitted successfully.",
                "student": result.data[0],
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Admission failed: {str(e)}")


@router.post("/teacher")
async def admit_teacher(
    payload: TeacherAdmitRequest, 
    current_user: dict = Depends(get_current_user)
):
    """
    Onboards a new staff member.
    Secure: Generates unique codes and assigns to the correct school.
    """
    check_admin_auth(current_user)
    db = get_supabase()
    school_id = current_user["school_id"]

    # 1. Unique Teacher Code Strategy (3 letters + 4 digits)
    clean = payload.full_name.replace(" ", "").upper()
    prefix = clean[:3] if len(clean) >= 3 else clean.ljust(3, "X")
    
    # Retry logic for code collisions
    code = prefix + ''.join(random.choices(string.digits, k=4))
    for _ in range(5):
        existing = db.table("teachers").select("id").eq("teacher_code", code).execute()
        if not existing.data:
            break
        code = prefix + ''.join(random.choices(string.digits, k=4))

    data = {
        "school_id": school_id,
        "name": payload.full_name.strip(),
        "teacher_code": code,
        "role": payload.role or "teacher",
    }
    
    try:
        result = db.table("teachers").insert(data).execute()
        if result.data:
            # Audit log
            log_action(
                school_id=school_id,
                action="TEACHER_ONBOARDED",
                actor_id=current_user["id"],
                actor_name=current_user["name"],
                entity_type="teacher",
                entity_id=result.data[0]["id"],
                new_value=data
            )
            
            # Increment teacher count
            db.rpc("increment_teacher_count", {"p_school_id": school_id}).execute()

            return {
                "message": f"Staff member {payload.full_name} onboarded.",
                "teacher": result.data[0],
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Staff onboarding failed: {str(e)}")
