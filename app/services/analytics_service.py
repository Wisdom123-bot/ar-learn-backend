from app.core.database import get_supabase
from app.utils.cache import get_cache, set_cache, invalidate_cache
import json


def get_school_overview(school_id: str):
    """Return school-wide analytics: mean scores, best/worst classes and subjects."""
    cache_key = f"school_overview:{school_id}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    db = get_supabase()

    # Fetch all results for this school (via students)
    results = (
        db.table("results")
        .select("score, subject_id, class_id, student_id, term")
        .in_("student_id", db.table("students").select("id").eq("school_id", school_id).execute().data and [s["id"] for s in db.table("students").select("id").eq("school_id", school_id).execute().data] or [])
        .execute()
    )
    # Easier: fetch all students of school, then results of those students
    student_ids = [s["id"] for s in db.table("students").select("id").eq("school_id", school_id).execute().data]
    if not student_ids:
        return {"school_mean": 0, "class_means": [], "subject_means": []}

    results_query = (
        db.table("results")
        .select("score, subject_id, class_id, student_id, term")
        .in_("student_id", student_ids)
        .execute()
    )
    rows = results_query.data or []

    # Overall school mean
    school_mean = sum(r["score"] for r in rows) / len(rows) if rows else 0

    # Class means
    class_scores = {}
    for r in rows:
        cid = r["class_id"]
        class_scores.setdefault(cid, []).append(r["score"])
    class_means = []
    for cid, scores in class_scores.items():
        class_name = db.table("classes").select("name").eq("id", cid).execute().data[0]["name"] if db.table("classes").select("name").eq("id", cid).execute().data else cid
        mean = sum(scores) / len(scores)
        class_means.append({"class_id": cid, "class_name": class_name, "mean_score": round(mean, 2)})
    class_means.sort(key=lambda x: x["mean_score"], reverse=True)

    # Subject means
    subject_scores = {}
    for r in rows:
        sid = r["subject_id"]
        subject_scores.setdefault(sid, []).append(r["score"])
    subject_means = []
    for sid, scores in subject_scores.items():
        subj_name = db.table("subjects").select("name").eq("id", sid).execute().data[0]["name"] if db.table("subjects").select("name").eq("id", sid).execute().data else sid
        mean = sum(scores) / len(scores)
        subject_means.append({"subject_id": sid, "subject_name": subj_name, "mean_score": round(mean, 2)})
    subject_means.sort(key=lambda x: x["mean_score"], reverse=True)

    data = {
        "school_mean": round(school_mean, 2),
        "best_class": class_means[0] if class_means else None,
        "worst_class": class_means[-1] if class_means else None,
        "best_subject": subject_means[0] if subject_means else None,
        "worst_subject": subject_means[-1] if subject_means else None,
        "class_means": class_means,
        "subject_means": subject_means,
    }
    set_cache(cache_key, data, ttl=300)
    return data


def get_class_subject_performance(school_id: str, term: str):
    """Fetch average scores per subject for each class in a specific term."""
    db = get_supabase()
    # 1. Get all students of school
    students = db.table("students").select("id").eq("school_id", school_id).execute().data
    if not students:
        return {}

    student_ids = [s["id"] for s in students]

    # 2. Fetch results for these students in the specific term
    results = (
        db.table("results")
        .select("score, subject_id, class_id")
        .in_("student_id", student_ids)
        .eq("term", term)
        .execute()
        .data or []
    )

    # 3. Aggregate scores by class and subject
    # { class_id: { subject_id: [scores] } }
    performance = {}
    for r in results:
        cid = r["class_id"]
        sid = r["subject_id"]
        performance.setdefault(cid, {}).setdefault(sid, []).append(r["score"])

    # 4. Compute means
    class_subject_means = {}
    for cid, subjects in performance.items():
        class_subject_means[cid] = {}
        for sid, scores in subjects.items():
            mean = sum(scores) / len(scores)
            class_subject_means[cid][sid] = round(mean, 2)

    return class_subject_means


def get_class_analytics(class_id: str):
    """Detailed analytics for a single class."""
    cache_key = f"class_analytics:{class_id}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    db = get_supabase()
    # Get all students in class
    students = db.table("students").select("id, name").eq("class_id", class_id).execute().data
    if not students:
        return {"class_mean": 0, "students": []}

    student_ids = [s["id"] for s in students]
    results = db.table("results").select("*").in_("student_id", student_ids).execute().data or []

    # Compute per-student means
    student_means = {}
    for r in results:
        sid = r["student_id"]
        student_means.setdefault(sid, []).append(r["score"])
    student_list = []
    for s in students:
        scores = student_means.get(s["id"], [])
        mean = sum(scores) / len(scores) if scores else 0
        student_list.append({"student_id": s["id"], "name": s["name"], "mean_score": round(mean, 2)})
    student_list.sort(key=lambda x: x["mean_score"], reverse=True)

    class_mean = sum(s["mean_score"] for s in student_list) / len(student_list) if student_list else 0

    data = {
        "class_mean": round(class_mean, 2),
        "student_count": len(student_list),
        "students": student_list,
    }
    set_cache(cache_key, data, ttl=300)
    return data