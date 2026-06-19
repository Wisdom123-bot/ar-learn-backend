from app.core.database import get_supabase
from app.utils.cache import get_cache, set_cache
from collections import defaultdict

def get_school_rankings(term: str):
    """
    Compute mean scores for ALL schools in the system for a specific term.
    Returns list of school stats sorted by mean.
    """
    cache_key = f"leaderboard_all:{term}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    db = get_supabase()

    # 1. Fetch all results for the term
    # We join with students and schools to get the school identity
    results = db.table("results").select("score, subject_id, students!inner(school_id, schools(name, county))").eq("term", term).eq("approval_status", "approved").execute().data or []

    school_data = defaultdict(lambda: {"total_score": 0, "count": 0, "name": "", "county": "", "subjects": defaultdict(lambda: {"total": 0, "count": 0})})

    for r in results:
        student = r["students"]
        sid = student["school_id"]
        s_info = student["schools"]
        
        school_data[sid]["name"] = s_info["name"]
        school_data[sid]["county"] = s_info["county"]
        school_data[sid]["total_score"] += r["score"]
        school_data[sid]["count"] += 1
        
        sub_id = r["subject_id"]
        school_data[sid]["subjects"][sub_id]["total"] += r["score"]
        school_data[sid]["subjects"][sub_id]["count"] += 1

    # 2. Finalize means
    leaderboard = []
    for sid, data in school_data.items():
        if data["count"] > 0:
            school_mean = data["total_score"] / data["count"]
            
            # Subject means
            subject_means = {}
            for sub_id, sub_data in data["subjects"].items():
                subject_means[sub_id] = round(sub_data["total"] / sub_data["count"], 2)

            leaderboard.append({
                "school_id": sid,
                "school_name": data["name"],
                "county": data["county"],
                "school_mean": round(school_mean, 2),
                "subject_means": subject_means,
                "entry_count": data["count"]
            })

    # Sort by mean descending
    leaderboard.sort(key=lambda x: x["school_mean"], reverse=True)
    
    # Fetch subject names to make IDs readable
    all_subject_ids = set()
    for entry in leaderboard:
        all_subject_ids.update(entry["subject_means"].keys())
    
    subjects_info = db.table("subjects").select("id, name").in_("id", list(all_subject_ids)).execute().data or []
    subject_map = {s["id"]: s["name"] for s in subjects_info}

    # Assign ranks and map names
    for i, entry in enumerate(leaderboard):
        entry["national_rank"] = i + 1
        readable_subjects = {}
        for sid, mean in entry["subject_means"].items():
            name = subject_map.get(sid, sid)
            readable_subjects[name] = mean
        entry["subject_means_readable"] = readable_subjects

    set_cache(cache_key, leaderboard, ttl=600)
    return leaderboard
