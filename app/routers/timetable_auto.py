from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
import random
from app.core.database import get_supabase

router = APIRouter(prefix="/timetable-auto", tags=["timetable-auto"])


class BreakTime(BaseModel):
    start_time: str  # HH:MM
    end_time: str    # HH:MM
    label: str       # e.g. "Morning Break", "Lunch Break"


class TimetableConfig(BaseModel):
    start_time: str = "08:00"
    end_time: str = "15:30"
    period_duration: int = 40            # minutes
    breaks: List[BreakTime] = []
    prioritize_weak_subjects: bool = False
    previous_term: Optional[str] = None  # e.g. "Term 3 2024"


def time_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def minutes_to_time(m: int) -> str:
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}"


def generate_time_slots(config: TimetableConfig) -> List[tuple]:
    """Generate list of (start_time, end_time) tuples for periods, excluding breaks."""
    day_start = time_to_minutes(config.start_time)
    day_end = time_to_minutes(config.end_time)
    period_len = config.period_duration

    # Parse break intervals as sets of minutes
    break_intervals = []
    for b in config.breaks:
        b_start = time_to_minutes(b.start_time)
        b_end = time_to_minutes(b.end_time)
        break_intervals.append((b_start, b_end))

    slots = []
    current = day_start
    while current + period_len <= day_end:
        slot_end = current + period_len
        # Check if this slot overlaps any break
        overlaps = False
        for bs, be in break_intervals:
            if not (slot_end <= bs or current >= be):
                overlaps = True
                break
        if not overlaps:
            slots.append((minutes_to_time(current), minutes_to_time(slot_end)))
        current += period_len
    return slots


@router.post("/generate/{school_id}")
async def generate_timetable(school_id: str, config: TimetableConfig):
    db = get_supabase()

    # 1. Get all classes
    classes = db.table("classes").select("id").eq("school_id", school_id).execute().data
    if not classes:
        raise HTTPException(status_code=404, detail="No classes found in this school")

    # 2. Get teacher assignments
    assignments = (
        db.table("teacher_class_subjects")
        .select("teacher_id, class_id, subject_id")
        .in_("class_id", [c["id"] for c in classes])
        .execute().data or []
    )
    if not assignments:
        raise HTTPException(status_code=400, detail="No teacher assignments found. Assign teachers to classes/subjects first.")

    # Build teacher map
    teacher_map = {}
    for a in assignments:
        key = (a["class_id"], a["subject_id"])
        teacher_map.setdefault(key, []).append(a["teacher_id"])

    # 3. If prioritize weak subjects, fetch weakest subjects for the school from previous term
    weak_subjects = set()
    if config.prioritize_weak_subjects and config.previous_term:
        try:
            from app.services.analytics_service import get_school_overview
            overview = get_school_overview(school_id)
            worst_subj = overview.get("worst_subject")
            if worst_subj:
                # Fetch subject ID
                subj = db.table("subjects").select("id").eq("name", worst_subj["subject_name"]).single().execute()
                if subj.data:
                    weak_subjects.add(subj.data["id"])
        except Exception:
            pass  # silently ignore if analytics not available

    # 4. Generate time slots
    slots = generate_time_slots(config)
    if len(slots) < 3:
        raise HTTPException(status_code=400, detail="Not enough time slots with the given configuration. Reduce break times or extend school hours.")

    # 5. Clear existing timetable for these classes
    db.table("timetable_entries").delete().in_("class_id", [c["id"] for c in classes]).execute()

    # 6. Generate timetable per class
    entries = []
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    total_slots = len(slots) * len(days)

    for cls in classes:
        class_id = cls["id"]
        # Gather subjects for this class
        class_subjects = set()
        for a in assignments:
            if a["class_id"] == class_id:
                class_subjects.add(a["subject_id"])
        if not class_subjects:
            continue

        subject_list = list(class_subjects)
        # If weak subjects exist, give them double weight (appear twice)
        weighted = []
        for s in subject_list:
            weighted.append(s)
            if s in weak_subjects:
                weighted.append(s)   # extra slot
        random.shuffle(weighted)

        slot_idx = 0
        for day in days:
            for slot in slots:
                if slot_idx >= len(weighted):
                    break
                subject_id = weighted[slot_idx % len(weighted)]
                teachers = teacher_map.get((class_id, subject_id), [])
                if not teachers:
                    slot_idx += 1
                    continue
                teacher_id = random.choice(teachers)
                entries.append({
                    "school_id": school_id,
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "teacher_id": teacher_id,
                    "day_of_week": day,
                    "start_time": slot[0],
                    "end_time": slot[1],
                })
                slot_idx += 1

    if not entries:
        raise HTTPException(status_code=400, detail="Could not generate any timetable entries. Check assignments and configuration.")

    # 7. Batch insert
    db.table("timetable_entries").insert(entries).execute()

    return {"message": f"Timetable generated for {len(classes)} classes with {len(entries)} entries"}