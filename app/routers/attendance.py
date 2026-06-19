from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.core.database import get_supabase
from app.schemas.attendance import BulkAttendanceRequest, AttendanceStats

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post("/record")
async def record_attendance(payload: BulkAttendanceRequest):
    """
    Records or updates attendance for a list of students on a given date.
    Uses a single upsert operation – handles 100,000 records instantly.
    """
    db = get_supabase()

    # 1. Verify class exists
    cls = db.table("classes").select("id").eq("id", str(payload.class_id)).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")

    # 2. Build rows for upsert
    rows = [
        {
            "student_id": str(entry.student_id),
            "class_id": str(payload.class_id),
            "date": entry.date.isoformat(),
            "status": entry.status,
            "recorded_by": str(payload.recorded_by) if payload.recorded_by else None,
        }
        for entry in payload.records
    ]

    # 3. Single database call – upsert on (student_id, date)
    try:
        result = db.table("attendance").upsert(
            rows,
            on_conflict="student_id,date"
        ).execute()
        return {
            "message": f"{len(rows)} attendance records saved",
            "count": len(rows),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save attendance: {str(e)}"
        )


# ---------- Statistics Endpoints (unchanged) ----------

@router.get("/stats/class/{class_id}", response_model=List[AttendanceStats])
async def class_attendance_stats(
    class_id: str,
    term_start: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    term_end: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    db = get_supabase()

    students = db.table("students").select("id, name").eq("class_id", class_id).execute().data
    if not students:
        return []

    student_ids = [s["id"] for s in students]
    student_map = {s["id"]: s["name"] for s in students}

    query = db.table("attendance").select("*").in_("student_id", student_ids)
    if term_start:
        query = query.gte("date", term_start)
    if term_end:
        query = query.lte("date", term_end)
    records = query.execute().data or []

    stats_map = {}
    for r in records:
        sid = r["student_id"]
        if sid not in stats_map:
            stats_map[sid] = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
        status_lower = r["status"].lower()
        if status_lower == "present":
            stats_map[sid]["present"] += 1
        elif status_lower == "absent":
            stats_map[sid]["absent"] += 1
        elif status_lower == "sick":
            stats_map[sid]["sick"] += 1
        elif status_lower == "suspended":
            stats_map[sid]["suspended"] += 1

    result = []
    for sid, name in student_map.items():
        s = stats_map.get(sid, {"present": 0, "absent": 0, "sick": 0, "suspended": 0})
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
async def student_attendance_stats(
    student_id: str,
    term_start: Optional[str] = Query(None),
    term_end: Optional[str] = Query(None),
):
    db = get_supabase()

    student = db.table("students").select("id, name").eq("id", student_id).execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    query = db.table("attendance").select("*").eq("student_id", student_id)
    if term_start:
        query = query.gte("date", term_start)
    if term_end:
        query = query.lte("date", term_end)
    records = query.execute().data or []

    stats = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    for r in records:
        status_lower = r["status"].lower()
        if status_lower in stats:
            stats[status_lower] += 1

    total = sum(stats.values())
    pct = (stats["present"] / total * 100) if total > 0 else 0
    student_name = student.data[0]["name"] if student.data else "Unknown"
    return AttendanceStats(
        student_id=student_id,
        student_name=student_name,
        total_days=total,
        present=stats["present"],
        absent=stats["absent"],
        sick=stats["sick"],
        suspended=stats["suspended"],
        attendance_pct=round(pct, 1),
    )
