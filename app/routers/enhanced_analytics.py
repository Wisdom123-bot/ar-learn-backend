from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from uuid import UUID
from typing import Optional, List
from app.core.database import get_supabase
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

    class_means = []
    for cls in classes:
        student_ids = [s["id"] for s in db.table("students").select("id").eq("class_id", cls["id"]).execute().data]
        if not student_ids:
            class_means.append(ClassRank(class_id=cls["id"], class_name=cls["name"], mean_score=0, rank=0))
            continue
        results = db.table("results").select("score").in_("student_id", student_ids).eq("term", term).execute().data or []
        mean = sum(r["score"] for r in results) / len(results) if results else 0
        class_means.append(ClassRank(class_id=cls["id"], class_name=cls["name"], mean_score=round(mean, 2), rank=0))

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
    subjects = db.table("subjects").select("id, name").eq("school_id", school_id).execute().data or []
    if not subjects:
        return []

    # Get all students for this school
    student_ids = [s["id"] for s in db.table("students").select("id").eq("school_id", school_id).execute().data]
    if not student_ids:
        return []

    subject_means = []
    for subj in subjects:
        results = (
            db.table("results")
            .select("score")
            .in_("student_id", student_ids)
            .eq("subject_id", subj["id"])
            .eq("term", term)
            .execute()
            .data or []
        )
        mean = sum(r["score"] for r in results) / len(results) if results else 0
        subject_means.append(SubjectRank(
            subject_id=subj["id"],
            subject_name=subj["name"],
            mean_score=round(mean, 2)
        ))

    # Sort by mean descending
    subject_means.sort(key=lambda x: x.mean_score, reverse=True)
    return subject_means


@router.put("/class/{class_id}/target-mean")
async def update_target_mean(class_id: str, payload: TargetMeanRequest):
    db = get_supabase()
    result = db.table("classes").update({"target_mean_score": payload.target_mean_score}).eq("id", class_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Class not found")
    return {"message": "Target mean updated"}