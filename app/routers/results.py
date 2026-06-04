import asyncio
from fastapi import APIRouter, HTTPException, status
from app.core.database import get_supabase
from app.schemas.result import BulkResultRequest
from app.services.notification_service import create_notification

router = APIRouter(prefix="/results", tags=["results"])

CHUNK_SIZE = 5000   # safe batch size for Supabase


@router.post("/submit")
async def submit_results(payload: BulkResultRequest):
    db = get_supabase()

    # 1. Verify teacher and get school
    teacher = (
        db.table("teachers")
        .select("id, name, school_id")
        .eq("id", str(payload.teacher_id))
        .single()
        .execute()
    )
    if not teacher.data:
        raise HTTPException(status_code=404, detail="Teacher not found")

    teacher_id = str(payload.teacher_id)
    teacher_name = teacher.data["name"]
    school_id = teacher.data["school_id"]

    # 2. Collect unique IDs from payload
    class_ids = list({str(e.class_id) for e in payload.results})
    subject_ids = list({str(e.subject_id) for e in payload.results})
    student_ids = list({str(e.student_id) for e in payload.results})

    # 3. Fetch teacher assignments in one query
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

    # 4. Fetch students in one query
    students = (
        db.table("students")
        .select("id, class_id")
        .in_("id", student_ids)
        .execute()
        .data or []
    )
    student_class = {s["id"]: s["class_id"] for s in students}

    # 5. In‑memory validation
    for entry in payload.results:
        cid = str(entry.class_id)
        sid = str(entry.subject_id)
        st_id = str(entry.student_id)

        if (cid, sid) not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Teacher not assigned to class {cid} for subject {sid}",
            )
        if st_id not in student_class or student_class[st_id] != cid:
            raise HTTPException(
                status_code=400,
                detail=f"Student {st_id} does not belong to class {cid}",
            )

    # 6. Prepare all rows
    rows = [
        {
            "student_id": str(e.student_id),
            "subject_id": str(e.subject_id),
            "class_id": str(e.class_id),
            "exam_type": e.exam_type,
            "term": payload.term,
            "academic_year": payload.academic_year,
            "score": e.score,
            "remarks": e.remarks,
            "submitted_by": teacher_id,
        }
        for e in payload.results
    ]

    # 7. Chunked insert
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
                detail=f"Insert failed in chunk {i//CHUNK_SIZE + 1}: {str(e)}",
            )

    # 8. Notify admins (sync is fine for a few admins)
    admins = (
        db.table("teachers")
        .select("id")
        .eq("school_id", school_id)
        .in_("role", ["headteacher", "dean"])
        .execute()
        .data or []
    )
    for admin in admins:
        create_notification(
            school_id=school_id,
            teacher_id=admin["id"],
            title="New Results Submitted",
            message=f"{teacher_name} submitted {inserted} results for {payload.term}.",
            category="result",
        )
    create_notification(
        school_id=school_id,
        title="Results Submitted",
        message=f"{inserted} results submitted by {teacher_name}.",
        category="result",
    )

    # 9. ML training in the background (non‑blocking)
    try:
        from app.services.ml_risk_service import train_model_async as ml_train
        asyncio.create_task(
            asyncio.to_thread(ml_train, school_id)  # runs in thread, doesn't block
        )
    except Exception:
        pass

    return {"message": f"{inserted} results submitted successfully", "count": inserted}