from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel
from app.core.database import get_supabase
from app.schemas.teacher import TeacherAssignRequest
from app.schemas.student import StudentBrief
from app.dependencies import get_current_user

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.put("/{teacher_id}/assign")
async def assign_teacher(
    teacher_id: str, 
    payload: TeacherAssignRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Assigns a teacher to multiple class-subject pairs.
    Secure: Verifies all classes/subjects belong to the administrator's school.
    """
    # 1. Admin Authorization Check
    if current_user["role"] not in ("headteacher", "dean"):
        raise HTTPException(status_code=403, detail="Forbidden: Admin role required for staff assignments.")
    
    db = get_supabase()
    school_id = current_user["school_id"]

    # 2. Verify target teacher exists and belongs to the same school
    target_teacher = db.table("teachers").select("id, school_id").eq("id", teacher_id).single().execute()
    if not target_teacher.data:
        raise HTTPException(status_code=404, detail="Target staff member not found.")
    
    if target_teacher.data["school_id"] != school_id:
        raise HTTPException(status_code=403, detail="Access denied: Staff member belongs to another institution.")

    # 3. Comprehensive ownership validation for all assignments
    for assignment in payload.assignments:
        # Check Class ownership
        cls = db.table("classes").select("id").eq("id", str(assignment.class_id)).eq("school_id", school_id).execute()
        if not cls.data:
            raise HTTPException(status_code=400, detail=f"Invalid Assignment: Class {assignment.class_id} not found in your school.")
        
        # Check Subject ownership
        subject = db.table("subjects").select("id").eq("id", str(assignment.subject_id)).eq("school_id", school_id).execute()
        if not subject.data:
            raise HTTPException(status_code=400, detail=f"Invalid Assignment: Subject {assignment.subject_id} not found in your school.")

    # 4. Atomic Replace: Remove old and insert new assignments
    try:
        db.table("teacher_class_subjects").delete().eq("teacher_id", teacher_id).execute()

        insert_data = [
            {
                "teacher_id": teacher_id,
                "class_id": str(assignment.class_id),
                "subject_id": str(assignment.subject_id),
                "is_class_teacher": assignment.is_class_teacher,
            }
            for assignment in payload.assignments
        ]
        
        if insert_data:
            db.table("teacher_class_subjects").insert(insert_data).execute()

        return {"message": f"Successfully updated {len(payload.assignments)} staff assignments."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assignment engine failure: {str(e)}")


@router.get("/{teacher_id}/profile")
async def get_teacher_profile(
    teacher_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves enriched profile data.
    Secure: Verifies cross-school boundaries.
    """
    db = get_supabase()

    # 1. Fetch teacher info and verify school
    teacher_res = db.table("teachers").select("id, name, teacher_code, role, phone, school_id").eq("id", teacher_id).single().execute()
    if not teacher_res.data:
        raise HTTPException(status_code=404, detail="Staff record not found.")
    
    t = teacher_res.data
    if t["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    school = db.table("schools").select("name").eq("id", t["school_id"]).single().execute()
    school_name = school.data["name"] if school.data else ""

    # 2. Assignments (Joined)
    assignments = db.table("teacher_class_subjects").select("*, classes(name), subjects(name)").eq("teacher_id", teacher_id).execute().data or []
    enriched_assignments = [
        {
            "class_name": a["classes"]["name"] if a.get("classes") else "Unknown",
            "subject_name": a["subjects"]["name"] if a.get("subjects") else "Unknown",
            "is_class_teacher": a["is_class_teacher"],
        }
        for a in assignments
    ]

    # 3. Timetable
    timetable = db.table("timetable_entries").select("day_of_week, start_time, end_time, subjects(name)").eq("teacher_id", teacher_id).order("day_of_week, start_time").execute().data or []

    return {
        "teacher": {
            "id": t["id"],
            "name": t["name"],
            "teacher_code": t["teacher_code"],
            "role": t["role"],
            "phone": t.get("phone", ""),
            "school_name": school_name,
        },
        "assignments": enriched_assignments,
        "timetable": timetable,
    }


@router.get("/{teacher_id}/assignments")
async def get_teacher_assignments(
    teacher_id: str,
    current_user: dict = Depends(get_current_user)
):
    db = get_supabase()
    
    # Ownership Check
    target = db.table("teachers").select("school_id").eq("id", teacher_id).single().execute()
    if not target.data or target.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = db.table("teacher_class_subjects").select("*, classes(name), subjects(name)").eq("teacher_id", teacher_id).execute()
    data = result.data or []
    for a in data:
        a["class_name"] = a["classes"]["name"] if a.get("classes") else "Unknown"
        a["subject_name"] = a["subjects"]["name"] if a.get("subjects") else "Unknown"
    return data


class PhoneUpdate(BaseModel):
    phone: str

@router.put("/{teacher_id}/phone")
async def update_teacher_phone(
    teacher_id: str, 
    payload: PhoneUpdate,
    current_user: dict = Depends(get_current_user)
):
    if teacher_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You can only update your own phone number.")
        
    db = get_supabase()
    result = db.table("teachers").update({"phone": payload.phone}).eq("id", teacher_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return {"message": "Identity record updated."}


@router.get("/{teacher_id}/students", response_model=List[StudentBrief])
async def get_assigned_students(
    teacher_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Optimized assignment query.
    Secure: Scoped to current school.
    """
    db = get_supabase()

    # 1. Verification
    if teacher_id != current_user["id"] and current_user["role"] not in ("headteacher", "dean"):
         raise HTTPException(status_code=403, detail="Forbidden")

    # 2. Find Class IDs
    assignments = db.table("teacher_class_subjects").select("class_id").eq("teacher_id", teacher_id).execute()
    if not assignments.data:
        return []

    class_ids = list({a["class_id"] for a in assignments.data})

    # 3. Batch Fetch Students (No N+1)
    result = db.table("students").select("*, classes(name)").in_("class_id", class_ids).eq("school_id", current_user["school_id"]).execute()
    data = result.data or []

    return [
        StudentBrief(
            id=s["id"],
            name=s["name"],
            admission_number=s["admission_number"],
            class_id=s["class_id"],
            class_name=s["classes"]["name"] if s.get("classes") else "Unknown",
        )
        for s in data
    ]
