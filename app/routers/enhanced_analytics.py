from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from uuid import UUID
from typing import Optional, List, Dict

from app.core.database import get_supabase
from app.services.leaderboard_service import get_school_rankings
from collections import defaultdict

router = APIRouter(prefix="/analytics", tags=["enhanced-analytics"])


class GrowthScore(BaseModel):
    student_id: UUID
    student_name: str
    previous_mean: float
    current_mean: float
    change: float


class ClassRank(BaseModel):
    class_id: UUID
    class_name: str
    mean_score: float
    rank: int


class SubjectRank(BaseModel):
    subject_id: UUID
    subject_name: str
    mean_score: float


class TargetMeanRequest(BaseModel):
    target_mean_score: float


@router.get("/student-growth")
async def student_growth(
    school_id: str = Query(...),
    current_term: str = Query(..., description="e.g. 'Term 1 2025'"),
    previous_term: str = Query(..., description="e.g. 'Term 3 2024'"),
    class_id: Optional[str] = Query(None),
):
    db = get_supabase()
    # Get students (optionally filtered by class)
    query = db.table("students").select("id, name, class_id").eq("school_id", school_id)
    if class_id:
        query = query.eq("class_id", class_id)
    students = query.execute().data or []
    if not students:
        return []

    student_ids = [s["id"] for s in students]
    student_map = {s["id"]: s for s in students}

    # Current term results
    current_res = db.table("results").select("student_id, score").in_("student_id", student_ids).eq("term", current_term).execute().data or []
    current_means = defaultdict(list)
    for r in current_res:
        current_means[r["student_id"]].append(r["score"])

    # Previous term results
    previous_res = db.table("results").select("student_id, score").in_("student_id", student_ids).eq("term", previous_term).execute().data or []
    previous_means = defaultdict(list)
    for r in previous_res:
        previous_means[r["student_id"]].append(r["score"])

    growth_list = []
    for sid in student_ids:
        curr = current_means.get(sid)
        prev = previous_means.get(sid)
        if curr and prev:
            curr_avg = sum(curr) / len(curr)
            prev_avg = sum(prev) / len(prev)
            change = round(curr_avg - prev_avg, 2)
            growth_list.append(GrowthScore(
                student_id=sid,
                student_name=student_map[sid]["name"],
                previous_mean=round(prev_avg, 2),
                current_mean=round(curr_avg, 2),
                change=change,
            ))

    # Sort by change descending
    growth_list.sort(key=lambda x: x.change, reverse=True)
    return growth_list


@router.get("/class-ranking")
async def class_ranking(
    school_id: str = Query(...),
    term: str = Query(...),
):
    db = get_supabase()
    classes = db.table("classes").select("id, name").eq("school_id", school_id).execute().data or []
    if not classes:
        return []

    class_ids = [c["id"] for c in classes]
    
    # Fetch all results for these classes in one go
    all_results = db.table("results").select("score, class_id").in_("class_id", class_ids).eq("term", term).execute().data or []
    
    class_scores = defaultdict(list)
    for r in all_results:
        class_scores[r["class_id"]].append(r["score"])

    class_means = []
    for cls in classes:
        scores = class_scores.get(cls["id"], [])
        mean = sum(scores) / len(scores) if scores else 0
        class_means.append(ClassRank(
            class_id=cls["id"],
            class_name=cls["name"],
            mean_score=round(mean, 2),
            rank=0
        ))

    # Sort by mean descending
    class_means.sort(key=lambda x: x.mean_score, reverse=True)
    for i, c in enumerate(class_means):
        c.rank = i + 1
    return class_means


@router.get("/subject-ranking")
async def subject_ranking(
    school_id: str = Query(...),
    term: str = Query(...),
):
    db = get_supabase()
    
    # Get all classes for this school
    classes = db.table("classes").select("id").eq("school_id", school_id).execute().data or []
    class_ids = [c["id"] for c in classes]
    if not class_ids:
        return []

    # Fetch ALL results for the school in one go
    all_results = db.table("results").select("score, subject_id").in_("class_id", class_ids).eq("term", term).execute().data or []
    if not all_results:
        return []

    subject_scores = defaultdict(list)
    for r in all_results:
        subject_scores[r["subject_id"]].append(r["score"])

    # Fetch only the subjects that have results
    used_subject_ids = list(subject_scores.keys())
    subjects = db.table("subjects").select("id, name").in_("id", used_subject_ids).execute().data or []

    subject_means = []
    for subj in subjects:
        scores = subject_scores.get(subj["id"], [])
        mean = sum(scores) / len(scores) if scores else 0
        subject_means.append(SubjectRank(
            subject_id=subj["id"],
            subject_name=subj["name"],
            mean_score=round(mean, 2)
        ))

    # Sort by mean descending
    subject_means.sort(key=lambda x: x.mean_score, reverse=True)
    return subject_means


@router.get("/leaderboard")
async def school_leaderboard(
    school_id: str = Query(...),
    term: str = Query(...),
):
    """
    Returns rankings and comparison data for a specific school.
    """
    all_rankings = get_school_rankings(term)
    if not all_rankings:
        return {"message": "No data available for this term"}

    # Find current school
    my_entry = next((s for s in all_rankings if s["school_id"] == school_id), None)
    if not my_entry:
        return {"message": "School not found in rankings for this term"}

    # County rankings
    county = my_entry["county"]
    county_rankings = [s for s in all_rankings if s["county"] == county]
    for i, s in enumerate(county_rankings):
        s["county_rank"] = i + 1

    my_county_entry = next((s for s in county_rankings if s["school_id"] == school_id), None)

    return {
        "school_name": my_entry["school_name"],
        "county": county,
        "school_mean": my_entry["school_mean"],
        "national_rank": my_entry["national_rank"],
        "total_schools_national": len(all_rankings),
        "county_rank": my_county_entry.get("county_rank") if my_county_entry else None,
        "total_schools_county": len(county_rankings),
        "national_top_5": all_rankings[:5],
        "county_top_5": county_rankings[:5],
        "subject_means": my_entry.get("subject_means_readable", my_entry["subject_means"])
    }


@router.put("/class/{class_id}/target-mean")
async def update_target_mean(class_id: str, payload: TargetMeanRequest):
    db = get_supabase()
    result = db.table("classes").update({"target_mean_score": payload.target_mean_score}).eq("id", class_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Class not found")
    return {"message": "Target mean updated"}