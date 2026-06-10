from app.core.database import get_supabase
from app.services.llm_client import ask_llm
import json

async def generate_student_summary(student_id: str, term: str):
    db = get_supabase()
    
    # 1. Fetch comprehensive data
    # Results (including subject teacher remarks)
    results = db.table("results").select("*, subjects(name)").eq("student_id", student_id).eq("term", term).eq("approval_status", "approved").execute().data or []
    
    # Class teacher remarks
    ct_remarks = db.table("class_teacher_remarks").select("remark").eq("student_id", student_id).eq("term", term).execute().data or []
    ct_remark_text = " ".join([r["remark"] for r in ct_remarks])

    # Attendance
    attendance = db.table("attendance").select("status").eq("student_id", student_id).execute().data or []
    
    # Discipline
    discipline = db.table("discipline_records").select("category, description").eq("student_id", student_id).execute().data or []
    
    # Student name
    student = db.table("students").select("name").eq("id", student_id).single().execute().data
    name = student["name"] if student else "The student"

    # 2. Format context for LLM
    results_str = "\n".join([f"- {r['subjects']['name']}: {r['score']}% (Teacher: {r.get('remarks', 'N/A')})" for r in results])
    
    att_counts = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
    for a in attendance:
        key = a["status"].lower()
        if key in att_counts:
            att_counts[key] += 1
    total_days = sum(att_counts.values())
    att_str = f"Present: {att_counts['present']}, Absent: {att_counts['absent']}, Total tracked: {total_days}"
    
    disc_str = "\n".join([f"- {d['category']}: {d['description']}" for d in discipline]) or "No discipline records."

    prompt = (
        f"Generate a professional executive academic summary for {name} for {term}.\n\n"
        f"Performance Data & Subject Teacher Remarks:\n{results_str or 'No results data available.'}\n\n"
        f"Class Teacher Remarks: {ct_remark_text or 'No specific class teacher remark.'}\n\n"
        f"Attendance Summary: {att_str}\n\n"
        f"Discipline Records:\n{disc_str}\n\n"
        "Your task is to SUMMARIZE all these observations into one cohesive, high-level professional paragraph. "
        "Incorporate the feedback from both subject and class teachers to provide a balanced view of progress, effort, and conduct. "
        "Identify specific areas for improvement (weaknesses). "
        "Maintain a supportive yet realistic tone suitable for a school report card's principal/dean summary."
    )
    
    system = "You are an expert academic advisor. Provide a 3-4 sentence professional summary of a student's performance based on provided data."
    
    summary = await ask_llm(prompt, system=system)
    return summary
