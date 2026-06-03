import uuid
import random
import string
from fastapi import APIRouter, HTTPException, status
from app.core.database import get_supabase
from app.schemas.school import (
    SchoolRegistrationRequest,
    SchoolRegistrationResponse,
    ClassResponse,
    TeacherResponse,
)

router = APIRouter(prefix="/schools", tags=["schools"])

def generate_teacher_code(name: str) -> str:
    """Generate a unique teacher code: first 3 letters of name + 4 random digits."""
    clean = name.replace(" ", "").upper()
    prefix = clean[:3] if len(clean) >= 3 else clean.ljust(3, "X")
    suffix = "".join(random.choices(string.digits, k=4))
    return f"{prefix}{suffix}"

def insert_teacher(db, school_id: str, name: str, role: str) -> dict:
    """Insert a teacher with a unique code and return the record."""
    code = generate_teacher_code(name)
    attempts = 0
    while attempts < 10:
        existing = db.table("teachers").select("*").eq("teacher_code", code).execute()
        if not existing.data:
            break
        code = generate_teacher_code(name)
        attempts += 1
    data = {
        "school_id": school_id,
        "name": name.strip(),
        "teacher_code": code,
        "role": role,
    }
    result = db.table("teachers").insert(data).execute()
    if result.data:
        return result.data[0]
    raise HTTPException(status_code=500, detail=f"Failed to create {role}")

@router.post("/register", response_model=SchoolRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_school(payload: SchoolRegistrationRequest):
    db = get_supabase()

    # 1. Insert the school with duplicate check
    school_data = {
        "name": payload.school_name,
        "county": payload.county,
        "student_count": payload.number_of_students,
        "teacher_count": payload.number_of_teachers + (1 if payload.headteacher_name else 0) + (1 if payload.dean_name else 0),
    }
    try:
        school_result = db.table("schools").insert(school_data).execute()
    except Exception as e:
        if "unique_school_per_county" in str(e) or "duplicate key" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A school with this name already exists in this county."
            )
        raise HTTPException(status_code=500, detail="Failed to create school record.")
    
    if not school_result.data:
        raise HTTPException(status_code=500, detail="Failed to create school record.")
    school = school_result.data[0]
    school_id = school["id"]

    # 2. Insert classes
    class_records = []
    for cls in payload.classes:
        class_data = {
            "school_id": school_id,
            "name": cls.name,
            "target_mean_score": cls.target_mean_score or 0.0,
        }
        result = db.table("classes").insert(class_data).execute()
        if result.data:
            class_records.append(result.data[0])

    # 3. Insert Headteacher (if provided)
    headteacher_record = None
    if payload.headteacher_name:
        headteacher_record = insert_teacher(db, school_id, payload.headteacher_name, "headteacher")

    # 4. Insert Dean (if provided)
    dean_record = None
    if payload.dean_name:
        dean_record = insert_teacher(db, school_id, payload.dean_name, "dean")

    # 5. Insert other teachers
    teacher_records = []
    for teacher_name in payload.teacher_names:
        try:
            record = insert_teacher(db, school_id, teacher_name, "teacher")
            teacher_records.append(record)
        except HTTPException:
            continue  # skip if fails

    # Build response
    return SchoolRegistrationResponse(
        message="School registered successfully",
        school_id=school["id"],
        school_name=school["name"],
        county=school["county"],
        headteacher=TeacherResponse(**headteacher_record) if headteacher_record else None,
        dean=TeacherResponse(**dean_record) if dean_record else None,
        teachers=[TeacherResponse(**t) for t in teacher_records],
        classes=[ClassResponse(**c) for c in class_records],
    )

@router.get("/{school_id}/classes")
async def get_school_classes(school_id: str):
    db = get_supabase()
    return db.table("classes").select("id, name").eq("school_id", school_id).execute().data or []

@router.get("/{school_id}/teachers")
async def get_school_teachers(school_id: str):
    db = get_supabase()
    return db.table("teachers").select("id, name, teacher_code, role").eq("school_id", school_id).execute().data or []