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


@router.post("/register", response_model=SchoolRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_school(payload: SchoolRegistrationRequest):
    db = get_supabase()

    # 1. Insert the school
    school_data = {
        "name": payload.school_name,
        "county": payload.county,
        "student_count": payload.number_of_students,
        "teacher_count": payload.number_of_teachers,
    }
    school_result = db.table("schools").insert(school_data).execute()
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

    # 3. Insert teachers with unique codes
    teacher_records = []
    for teacher_name in payload.teacher_names:
        # Ensure unique code (very rare collisions, but we loop to be safe)
        code = generate_teacher_code(teacher_name)
        attempts = 0
        while attempts < 10:
            # Check if code already exists
            existing = db.table("teachers").select("*").eq("teacher_code", code).execute()
            if not existing.data:
                break
            code = generate_teacher_code(teacher_name)
            attempts += 1
        teacher_data = {
            "school_id": school_id,
            "name": teacher_name.strip(),
            "teacher_code": code,
        }
        result = db.table("teachers").insert(teacher_data).execute()
        if result.data:
            teacher_records.append(result.data[0])

    # 4. Build response
    return SchoolRegistrationResponse(
        message="School registered successfully",
        school_id=school["id"],
        school_name=school["name"],
        county=school["county"],
        classes=[ClassResponse(**c) for c in class_records],
        teachers=[TeacherResponse(**t) for t in teacher_records],
    )