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

    # Get all classes for this school to fetch all results in one go
    classes = db.table("classes").select("id").eq("school_id", school_id).execute().data or []
    class_ids = [c["id"] for c in classes]
    if not class_ids:
        return []

    # Fetch ALL results for the school for the relevant terms
    terms_to_fetch = [term]
    if previous_term:
        terms_to_fetch.append(previous_term)
    
    all_results = db.table("results").select("score, subject_id, student_id, term, submitted_by").in_("class_id", class_ids).in_("term", terms_to_fetch).execute().data or []
    
    # Pre-process results into useful maps
    teacher_current_results = defaultdict(list)
    teacher_previous_results = defaultdict(list)
    subject_school_scores = defaultdict(list)
    
    for r in all_results:
        t_id = r["submitted_by"]
        r_term = r["term"]
        score = r["score"]
        subj_id = r["subject_id"]
        
        if r_term == term:
            teacher_current_results[t_id].append(r)
            subject_school_scores[subj_id].append(score)
        elif r_term == previous_term:
            teacher_previous_results[t_id].append(r)

    teacher_results = []

    for teacher in teachers:
        tid = teacher["id"]
        current_res = teacher_current_results.get(tid, [])

        if not current_res:
            continue

        # Current mean
        current_scores = [r["score"] for r in current_res]
        current_mean = sum(current_scores) / len(current_scores)

        # Subject-specific school mean
        subjects_taught = list(set(r["subject_id"] for r in current_res))
        
        bench_scores = []
        for s_id in subjects_taught:
            bench_scores.extend(subject_school_scores.get(s_id, []))
            
        school_subject_mean = sum(bench_scores) / len(bench_scores) if bench_scores else None

        # Previous mean
        previous_mean = None
        change = None
        prev_res = teacher_previous_results.get(tid, [])
        if prev_res:
            prev_scores = [r["score"] for r in prev_res]
            previous_mean = sum(prev_scores) / len(prev_scores)
            change = current_mean - previous_mean

        # Value-add: NOW DEFINED AS Improvement from previous term
        # This is more standard in Kenyan systems.
        value_add = change if change is not None else 0

        # Peer Difference: How the teacher's students did vs school-wide avg for same subjects
        peer_difference = current_mean - school_subject_mean if school_subject_mean is not None else 0

        # Risk students
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
            "value_add": round(value_add, 2),
            "peer_difference": round(peer_difference, 2),
            "risk_student_count": risk_count,
            "subjects_taught": subjects_taught,
        })

    # Sort by value_add descending (best teachers first)
    # Ensure teachers with None value_add are at the bottom but not breaking sort
    teacher_results.sort(key=lambda x: (x["value_add"] is not None, x["value_add"] or -999), reverse=True)

    set_cache(cache_key, teacher_results, ttl=600)  # cache 10 min
    return teacher_results