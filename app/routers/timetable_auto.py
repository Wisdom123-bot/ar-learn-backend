import random
from fastapi import APIRouter, HTTPException
from app.core.database import get_supabase

router = APIRouter(prefix="/timetable-auto", tags=["timetable-auto"])

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
PERIODS = [
    ("08:00", "08:40"),
    ("08:40", "09:20"),
    ("09:20", "10:00"),
    ("10:20", "11:00"),
    ("11:00", "11:40"),
    ("11:40", "12:20"),
    ("13:00", "13:40"),
    ("13:40", "14:20"),
]

@router.post("/generate/{school_id}")
async def generate_timetable(school_id: str):
    db = get_supabase()

    # 1. Get all classes of the school
    classes = db.table("classes").select("id").eq("school_id", school_id).execute().data
    if not classes:
        raise HTTPException(status_code=404, detail="No classes found")

    # 2. Get all teacher-subject assignments for the school
    assignments = (
        db.table("teacher_class_subjects")
        .select("teacher_id, class_id, subject_id")
        .in_("class_id", [c["id"] for c in classes])
        .execute().data or []
    )
    if not assignments:
        raise HTTPException(status_code=400, detail="No teacher assignments found. Assign teachers to classes/subjects first.")

    # 3. Build a mapping: (class_id, subject_id) -> list of teacher_ids
    teacher_map = {}
    for a in assignments:
        key = (a["class_id"], a["subject_id"])
        teacher_map.setdefault(key, []).append(a["teacher_id"])

    # 4. Clear existing timetable for these classes
    db.table("timetable_entries").delete().in_("class_id", [c["id"] for c in classes]).execute()

    # 5. For each class, assign subjects to slots
    entries = []
    for cls in classes:
        class_id = cls["id"]
        # Get subjects taught in this class
        class_subjects = set()
        for a in assignments:
            if a["class_id"] == class_id:
                class_subjects.add(a["subject_id"])
        # Shuffle subjects to randomize
        subjects_list = list(class_subjects)
        random.shuffle(subjects_list)
        # Simple round-robin filling of the 8 periods × 5 days grid
        slot_index = 0
        for _ in range(len(PERIODS) * len(DAYS)):
            if slot_index >= len(subjects_list):
                break
            subject_id = subjects_list[slot_index % len(subjects_list)]
            day = DAYS[(slot_index // len(PERIODS)) % len(DAYS)]
            period = PERIODS[slot_index % len(PERIODS)]
            # Get a teacher for this subject in this class
            teachers = teacher_map.get((class_id, subject_id), [])
            if not teachers:
                slot_index += 1
                continue
            teacher_id = random.choice(teachers)
            entries.append({
                "school_id": school_id,
                "class_id": class_id,
                "subject_id": subject_id,
                "teacher_id": teacher_id,
                "day_of_week": day,
                "start_time": period[0],
                "end_time": period[1],
            })
            slot_index += 1

    # 6. Batch insert
    if entries:
        db.table("timetable_entries").insert(entries).execute()

    return {"message": f"Timetable generated for {len(classes)} classes with {len(entries)} entries"}