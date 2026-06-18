import random
import string
from fastapi import HTTPException, status
from app.core.database import get_supabase
from app.schemas.school import (
    SchoolRegistrationRequest,
    SchoolRegistrationResponse,
    ClassResponse,
    SubjectResponse,
    TeacherResponse,
)

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

import json

async def register_new_school(payload: SchoolRegistrationRequest):
    db = get_supabase()
    
    # Prepare data for RPC
    classes_json = [c.dict() for c in payload.classes]
    
    try:
        # Call the transactional RPC function
        rpc_result = db.rpc("register_school_transactional", {
            "p_school_name": payload.school_name,
            "p_county": payload.county,
            "p_email": payload.email,
            "p_phone": payload.phone,
            "p_student_count": payload.number_of_students,
            "p_teacher_count": payload.number_of_teachers + (1 if payload.headteacher_name else 0) + (1 if payload.dean_name else 0),
            "p_classes": classes_json,
            "p_subjects": payload.subjects,
            "p_headteacher_name": payload.headteacher_name,
            "p_dean_name": payload.dean_name,
            "p_teacher_names": payload.teacher_names
        }).execute()
        
        if rpc_result.data:
            data = rpc_result.data
            # We fetch minimal info for response model or refactor response model
            return SchoolRegistrationResponse(
                message=data["message"],
                school_id=data["school_id"],
                school_name=data["school_name"],
                county=payload.county,
                email=payload.email or "",
                phone=payload.phone or "",
                headteacher=None, # Simplified for RPC response, can be fetched if needed
                dean=None,
                teachers=[],
                classes=[],
                subjects=[]
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Atomic registration failed: {str(e)}"
        )
