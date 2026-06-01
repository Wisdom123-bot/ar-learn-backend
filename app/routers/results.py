from fastapi import APIRouter, HTTPException, status
from app.core.database import get_supabase
from app.schemas.result import BulkResultRequest
from app.services.notification_service import create_notification
from app.core.database import get_supabase as db_get  # we already have get_supabase

router = APIRouter(prefix="/results", tags=["results"])


@router.post("/submit")
async def submit_results(payload: BulkResultRequest):
    db = get_supabase()

    # 1. Check teacher exists
    teacher = db.table("teachers").select("*").eq("id", str(payload.teacher_id)).execute()
    if not teacher.data:
        raise HTTPException(status_code=404, detail="Teacher not found")

    teacher_id = str(payload.teacher_id)
    teacher_name = teacher.data[0]["name"]
    school_id = teacher.data[0]["school_id"]

    # 2. For each result, validate assignment and student
    for entry in payload.results:
        assignment = (
            db.table("teacher_class_subjects")
            .select("*")
            .eq("teacher_id", teacher_id)
            .eq("class_id", str(entry.class_id))
            .eq("subject_id", str(entry.subject_id))
            .execute()
        )
        if not assignment.data:
            raise HTTPException(
                status_code=403,
                detail=f"Teacher not assigned to class {entry.class_id} for subject {entry.subject_id}"
            )
        student = db.table("students").select("class_id").eq("id", str(entry.student_id)).execute()
        if not student.data or student.data[0]["class_id"] != str(entry.class_id):
            raise HTTPException(
                status_code=400,
                detail=f"Student {entry.student_id} does not belong to class {entry.class_id}"
            )

    # 3. Insert all results
    inserted = []
    for entry in payload.results:
        data = {
            "student_id": str(entry.student_id),
            "subject_id": str(entry.subject_id),
            "class_id": str(entry.class_id),
            "exam_type": entry.exam_type,
            "term": payload.term,
            "academic_year": payload.academic_year,
            "score": entry.score,
            "remarks": entry.remarks,
            "submitted_by": teacher_id,
        }
        result = db.table("results").insert(data).execute()
        if result.data:
            inserted.append(result.data[0])

    # 4. Notify headteacher and dean
    # Find headteacher(s) and dean(s) in this school
    admins = db.table("teachers").select("id").eq("school_id", school_id).in_("role", ["headteacher", "dean"]).execute().data or []
    for admin in admins:
        create_notification(
            school_id=school_id,
            teacher_id=admin["id"],
            title="New Results Submitted",
            message=f"{teacher_name} submitted {len(inserted)} results for {payload.term}.",
            category="result"
        )
    # Also a general school notification (teacher_id=None)
    create_notification(
        school_id=school_id,
        title="Results Submitted",
        message=f"{len(inserted)} results submitted by {teacher_name}.",
        category="result"
    )

    return {"message": f"{len(inserted)} results submitted successfully", "count": len(inserted)}
# After successful insertion, try to trigger ML training silently
try:
    from app.services.ml_risk_service import train_model_async
    train_model_async(school_id)
except Exception:
    pass  # ML failure must never affect the user