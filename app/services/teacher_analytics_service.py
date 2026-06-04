from app.core.database import get_supabase
from app.utils.cache import get_cache, set_cache
from collections import defaultdict

def compute_teacher_value_add(
    school_id: str,
    term: str,
    previous_term: str = None
) -> list[dict]:
    """
    For each teacher in a school, compute:
    - current_mean: average score of their students in the given term
    - previous_mean: average in previous term (if available)
    - change: difference between current and previous mean
    - school_subject_mean: average score of all students in the school for the subjects they teach
    - value_add: teacher_mean - school_subject_mean (positive = outperforming school average)
    - risk_student_count: students in their classes flagged as at risk (mean < 50)
    """
    cache_key = f"teacher_analytics:{school_id}:{term}:{previous_term}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    db = get_supabase()

    # Get all teachers in this school
    teachers = db.table("teachers").select("id, name").eq("school_id", school_id).execute().data
    if not teachers:
        return []

    # Get all student IDs of this school (for subject‑level school mean)
    school_students = db.table("students").select("id").eq("school_id", school_id).execute().data or []
    school_student_ids = [s["id"] for s in school_students]

    teacher_results = []

    for teacher in teachers:
        tid = teacher["id"]

        # Find all results submitted by this teacher for this term
        current_res = (
            db.table("results")
            .select("score, subject_id, student_id")
            .eq("submitted_by", tid)
            .eq("term", term)
            .execute()
            .data or []
        )

        if not current_res:
            continue  # teacher with no results in this term

        # Current mean
        current_scores = [r["score"] for r in current_res]
        current_mean = sum(current_scores) / len(current_scores)

        # Subject-specific school mean for the subjects this teacher taught
        subjects_taught = list(set(r["subject_id"] for r in current_res))
        school_subject_scores = []
        for subj_id in subjects_taught:
            subj_results = (
                db.table("results")
                .select("score")
                .eq("subject_id", subj_id)
                .eq("term", term)
                .in_("student_id", school_student_ids)
                .execute()
                .data or []
            )
            school_subject_scores.extend(r["score"] for r in subj_results)
        school_subject_mean = sum(school_subject_scores) / len(school_subject_scores) if school_subject_scores else None

        # Previous term mean (if provided)
        previous_mean = None
        change = None
        if previous_term:
            prev_res = (
                db.table("results")
                .select("score")
                .eq("submitted_by", tid)
                .eq("term", previous_term)
                .execute()
                .data or []
            )
            if prev_res:
                prev_scores = [r["score"] for r in prev_res]
                previous_mean = sum(prev_scores) / len(prev_scores)
                change = current_mean - previous_mean

        # Value-add: teacher mean minus school subject mean
        value_add = current_mean - school_subject_mean if school_subject_mean is not None else None

        # Risk students: students with mean score < 50 in the teacher's subjects
        student_scores = defaultdict(list)
        for r in current_res:
            student_scores[r["student_id"]].append(r["score"])
        risk_count = 0
        for sid, scores in student_scores.items():
            if sum(scores) / len(scores) < 50:
                risk_count += 1

        teacher_results.append({
            "teacher_id": tid,
            "teacher_name": teacher["name"],
            "current_mean": round(current_mean, 2),
            "previous_mean": round(previous_mean, 2) if previous_mean is not None else None,
            "change": round(change, 2) if change is not None else None,
            "school_subject_mean": round(school_subject_mean, 2) if school_subject_mean is not None else None,
            "value_add": round(value_add, 2) if value_add is not None else None,
            "risk_student_count": risk_count,
            "subjects_taught": subjects_taught,
        })

    # Sort by value_add descending (best teachers first)
    teacher_results.sort(key=lambda x: x["value_add"] if x["value_add"] is not None else -999, reverse=True)

    set_cache(cache_key, teacher_results, ttl=600)  # cache 10 min
    return teacher_results