from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from app.core.database import get_supabase
from app.schemas.result import BulkResultRequest
from app.services.notification_service import create_notification
from app.dependencies import get_current_user
from app.utils.security import sanitize_string, validate_uuid

router = APIRouter(prefix="/results", tags=["results"])

CHUNK_SIZE = 5000   # safe batch size for Supabase


@router.post("/submit")
async def submit_results(
    payload: BulkResultRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    db = get_supabase()
    # ... (skipping unchanged code for brevity, but I must provide full targetContent for replacement)

    # 1. Verify current user is the one submitting and get school context
    if str(payload.teacher_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You can only submit results for yourself.")
    
    teacher_id = current_user["id"]
    teacher_name = current_user["name"]
    school_id = current_user["school_id"]

    # 2. Collect unique IDs from payload for batch validation
    class_ids = list({str(e.class_id) for e in payload.results})
    subject_ids = list({str(e.subject_id) for e in payload.results})
    student_ids = list({str(e.student_id) for e in payload.results})

    # 3. Fetch teacher assignments in one query to verify permissions
    assignments = (
        db.table("teacher_class_subjects")
        .select("class_id, subject_id")
        .eq("teacher_id", teacher_id)
        .in_("class_id", class_ids)
        .in_("subject_id", subject_ids)
        .execute()
        .data or []
    )
    allowed = {(a["class_id"], a["subject_id"]) for a in assignments}

    # 4. Fetch students in one query to verify they belong to the correct school and class
    students = (
        db.table("students")
        .select("id, class_id, school_id")
        .in_("id", student_ids)
        .execute()
        .data or []
    )
    student_meta = {s["id"]: {"class_id": s["class_id"], "school_id": s["school_id"]} for s in students}

    # 5. Strict Validation: RBAC, School, and Class consistency
    for entry in payload.results:
        cid = str(entry.class_id)
        sid = str(entry.subject_id)
        st_id = str(entry.student_id)

        # Ensure teacher is assigned to this specific class-subject pair
        if (cid, sid) not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: You are not assigned to class {cid} for subject {sid}",
            )
        
        # Verify student exists and belongs to the teacher's school
        if st_id not in student_meta:
            raise HTTPException(status_code=404, detail=f"Student {st_id} not found.")
        
        if student_meta[st_id]["school_id"] != school_id:
            raise HTTPException(status_code=403, detail="Access denied: Student belongs to another institution.")
            
        # Ensure student is actually in the class they are being graded for
        if student_meta[st_id]["class_id"] != cid:
            raise HTTPException(
                status_code=400,
                detail=f"Data inconsistency: Student {st_id} does not belong to class {cid}",
            )

    # 6. Prepare all rows for bulk insert
    rows = [
        {
            "student_id": validate_uuid(e.student_id),
            "subject_id": validate_uuid(e.subject_id),
            "class_id": validate_uuid(e.class_id),
            "exam_type": e.exam_type,
            "term": sanitize_string(payload.term, 30),
            "academic_year": sanitize_string(payload.academic_year, 4),
            "score": e.score,
            "remarks": sanitize_string(e.remarks, 200),
            "submitted_by": teacher_id,
        }
        for e in payload.results
    ]

    # 7. Chunked insert for high performance and stability
    inserted = 0
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i : i + CHUNK_SIZE]
        try:
            result = db.table("results").insert(chunk).execute()
            if result.data:
                inserted += len(result.data)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Internal Database Error during submission: {str(e)}",
            )

    # 8. Notify school administration (Async)
    admins = (
        db.table("teachers")
        .select("id")
        .eq("school_id", school_id)
        .in_("role", ["headteacher", "dean"])
        .execute()
        .data or []
    )
    for admin in admins:
        background_tasks.add_task(
            create_notification,
            school_id=school_id,
            teacher_id=admin["id"],
            title="Academic Results Filed",
            message=f"{teacher_name} filed {inserted} student results for {payload.term}.",
            category="result",
        )

    # 9. Trigger background ML model refresh (Async)
    try:
        from app.services.ml_risk_service import train_model_async as ml_train
        background_tasks.add_task(ml_train, school_id)
    except Exception:
        pass

    return {"message": f"{inserted} results archived successfully", "count": inserted}
