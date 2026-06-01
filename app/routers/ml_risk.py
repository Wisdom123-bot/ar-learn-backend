from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.database import get_supabase
from app.services.ml_risk_service import predict_risk

router = APIRouter(prefix="/ml-risk", tags=["ml-risk"])


@router.get("/student/{student_id}")
async def student_ml_risk(
    student_id: str,
    term: str = Query(..., description="Current term, e.g. 'Term 1 2025'"),
):
    db = get_supabase()
    # Verify student exists
    student = db.table("students").select("id, name").eq("id", student_id).single().execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    # Get all subjects this student has results for in this term
    subjects = db.table("subjects").select("id, name").execute().data or []
    subject_risks = []
    for subj in subjects:
        risk = predict_risk(student_id, subj["id"], term)
        if risk is not None:
            subject_risks.append({
                "subject_id": subj["id"],
                "subject_name": subj["name"],
                "risk_probability": round(risk, 2),
            })

    if not subject_risks:
        return {"student_name": student.data["name"], "message": "No ML model available yet. Risk scores will appear after the system has enough data.", "subject_risks": []}

    overall = max(r["risk_probability"] for r in subject_risks) if subject_risks else 0
    subject_risks.sort(key=lambda x: x["risk_probability"], reverse=True)
    return {
        "student_name": student.data["name"],
        "subject_risks": subject_risks,
        "overall_risk": round(overall, 2),
    }


@router.get("/class/{class_id}")
async def class_ml_risk(
    class_id: str,
    term: str = Query(..., description="Current term, e.g. 'Term 1 2025'"),
):
    db = get_supabase()
    # Verify class exists
    cls = db.table("classes").select("id, name").eq("id", class_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found")

    students = db.table("students").select("id, name").eq("class_id", class_id).execute().data or []
    if not students:
        return {"class_name": cls.data[0]["name"], "students": [], "message": "No students in this class."}

    subjects = db.table("subjects").select("id, name").execute().data or []
    result = []
    for student in students:
        student_risks = []
        for subj in subjects:
            risk = predict_risk(student["id"], subj["id"], term)
            if risk is not None:
                student_risks.append({
                    "subject_name": subj["name"],
                    "risk_probability": round(risk, 2),
                })
        if student_risks:
            overall = max(r["risk_probability"] for r in student_risks)
            result.append({
                "student_id": student["id"],
                "student_name": student["name"],
                "subject_risks": sorted(student_risks, key=lambda x: x["risk_probability"], reverse=True),
                "overall_risk": round(overall, 2),
            })

    # Sort by overall risk descending
    result.sort(key=lambda x: x["overall_risk"], reverse=True)
    return {
        "class_name": cls.data[0]["name"],
        "students": result,
        "message": "No ML model available yet." if not result else "",
    }