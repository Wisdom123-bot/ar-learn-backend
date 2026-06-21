from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from typing import List, Optional
from app.core.database import get_supabase
from app.core.redis import cache_result
from app.schemas.attendance import BulkAttendanceRequest, AttendanceStats
from app.dependencies import get_current_user
from app.utils.security import sanitize_string, validate_uuid

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post("/record")
async def record_attendance(
    payload: BulkAttendanceRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Records or updates attendance for a list of students on a given date.
    Secure: Verifies class ownership.
    """
    db = get_supabase()

    # 1. Verify class exists and belongs to the teacher's school
    cls = db.table("classes").select("id, school_id").eq("id", str(payload.class_id)).single().execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found.")
    
    if cls.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Access denied: Class belongs to another school.")

    # 2. Build rows for upsert
    rows = [
        {
            "student_id": validate_uuid(entry.student_id),
            "class_id": validate_uuid(payload.class_id),
            "date": entry.date.isoformat(),
            "status": entry.status,
            "recorded_by": validate_uuid(current_user["id"]),
        }
        for entry in payload.records
    ]

    # 3. Single database call – upsert on (student_id, date)
    try:
        db.table("attendance").upsert(
            rows,
            on_conflict="student_id,date"
        ).execute()
        return {
            "message": f"Successfully archived {len(rows)} attendance records.",
            "count": len(rows),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Attendance archival failure: {str(e)}"
        )


@router.get("/stats/class/{class_id}", response_model=List[AttendanceStats])
@cache_result(expire=300, prefix="attendance") # Cache for 5 minutes
async def class_attendance_stats(
    class_id: str,
    term_start: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    term_end: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user)
):
    validate_uuid(class_id)
    safe_start = sanitize_string(term_start, 10) if term_start else None
    safe_end = sanitize_string(term_end, 10) if term_end else None
    """
    Optimized class statistics using batch fetching.
    Secure: Verifies school membership.
    """
    db = get_supabase()

    # 1. Verification
    cls = db.table("classes").select("school_id").eq("id", class_id).single().execute()
    if not cls.data or cls.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    # 2. Fetch all students in class
    students = db.table("students").select("id, name").eq("class_id", class_id).execute().data
    if not students:
        return []

    student_ids = [s["id"] for s in students]
    student_map = {s["id"]: s["name"] for s in students}

    # 3. Batch fetch all attendance records for these students in the period
    query = db.table("attendance").select("student_id, status").in_("student_id", student_ids)
    if term_start:
        query = query.gte("date", term_start)
    if term_end:
        query = query.lte("date", term_end)
    records = query.execute().data or []

    # 4. In-memory aggregation (O(N) instead of O(N^2))
    stats_map = {sid: {"present": 0, "absent": 0, "sick": 0, "suspended": 0} for sid in student_ids}
    
    for r in records:
        sid = r["student_id"]
        status_lower = r["status"].lower()
        if sid in stats_map and status_lower in stats_map[sid]:
            stats_map[sid][status_lower] += 1

    # 5. Build response
    result = []
    for sid, name in student_map.items():
        s = stats_map[sid]
        total = sum(s.values())
        pct = (s["present"] / total * 100) if total > 0 else 0
        result.append(AttendanceStats(
            student_id=sid,
            student_name=name,
            total_days=total,
            present=s["present"],
            absent=s["absent"],
            sick=s["sick"],
            suspended=s["suspended"],
            attendance_pct=round(pct, 1),
        ))

    result.sort(key=lambda x: x.attendance_pct)
    return result


@router.get("/stats/student/{student_id}", response_model=AttendanceStats)
@cache_result(expire=300, prefix="attendance") # Cache for 5 minutes
async def student_attendance_stats(
    student_id: str,
    term_start: Optional[str] = Query(None),
    term_end: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    validate_uuid(student_id)
    safe_start = sanitize_string(term_start, 10) if term_start else None
    safe_end = sanitize_string(term_end, 10) if term_end else None
    """
    Secure individual stats fetch.
    """
    db = get_supabase()

    # 1. Verify student school
    student = db.table("students").select("id, name, school_id").eq("id", student_id).single().execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found.")
    
    if student.data["school_id"] != current_user["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    # 2. Fetch records
    query = db.table("attendance").select("status").eq("student_id", student_id)
    if term_start:
        query = query.gte("date", term_start)
    if term_end:
        query = query.lte("date", term_end)
    records = query.execute().data or []

    # 3. Aggregate
    stats = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    for r in records:
        status_lower = r["status"].lower()
        if status_lower in stats:
            stats[status_lower] += 1

    total = sum(stats.values())
    pct = (stats["present"] / total * 100) if total > 0 else 0
    return AttendanceStats(
        student_id=student_id,
        student_name=student.data["name"],
        total_days=total,
        present=stats["present"],
        absent=stats["absent"],
        sick=stats["sick"],
        suspended=stats["suspended"],
        attendance_pct=round(pct, 1),
    )
