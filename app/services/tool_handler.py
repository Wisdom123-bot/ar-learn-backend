"""
Secure tool handler for Ar‑Learn AI Assistant.
All tools are READ‑ONLY, scoped to the user's school, and never expose credentials.
"""

from app.core.database import get_supabase
from typing import Optional


def execute_tool(tool_name: str, parameters: dict, context: dict) -> dict:
    """
    Execute a safe read‑only tool with optimized batch queries.
    """
    db = get_supabase()
    school_id = context["school_id"]
    role = context.get("role", "teacher")

    # ── Optimized Tool implementations ──

    if tool_name == "get_school_overview":
        from app.services.analytics_service import get_school_overview
        return get_school_overview(school_id)

    elif tool_name == "get_top_students":
        class_id = parameters.get("class_id")
        subject_id = parameters.get("subject_id")
        limit = min(int(parameters.get("limit", 5)), 20)
        term = parameters.get("term", "Term 1 2025")

        query = db.table("results").select("student_id, score").eq("term", term)
        if class_id:
            query = query.eq("class_id", class_id)
        if subject_id:
            query = query.eq("subject_id", subject_id)
        results = query.execute().data or []

        # Aggregate scores
        scores = {}
        for r in results:
            scores.setdefault(r["student_id"], []).append(r["score"])
        avg = [(sid, sum(sc)/len(sc)) for sid, sc in scores.items()]
        avg.sort(key=lambda x: x[1], reverse=True)

        top_ids = [sid for sid, _ in avg[:limit]]
        if not top_ids:
            return {"top_students": []}

        # BATCH FETCH students and their class names in one query
        students_res = db.table("students").select("id, name, classes(name)").in_("id", top_ids).eq("school_id", school_id).execute()
        student_map = {s["id"]: s for s in (students_res.data or [])}

        top = []
        for sid, mean in avg[:limit]:
            if sid in student_map:
                s = student_map[sid]
                top.append({
                    "student_name": s["name"],
                    "class_name": s["classes"]["name"] if s.get("classes") else "N/A",
                    "mean_score": round(mean, 2),
                })
        return {"top_students": top}

    elif tool_name == "get_student_profile":
        student_name = parameters.get("student_name")
        admission = parameters.get("admission_number")
        if not student_name and not admission:
            return {"error": "Provide student_name or admission_number"}

        # Optimized: Fetch student info and essential linked data in one shot
        query = db.table("students").select("id, name, admission_number, classes(name)").eq("school_id", school_id)
        if admission:
            query = query.eq("admission_number", admission)
        else:
            query = query.ilike("name", f"%{student_name}%")
        student = query.limit(1).single().execute()

        if not student.data:
            return {"error": "Student not found"}

        sid = student.data["id"]
        term = parameters.get("term", "Term 1 2025")

        # BATCH FETCH profile details (results with subjects, attendance, and fees)
        # We can use the nested logic similar to the router optimization
        details = db.table("students").select("""
            results(*, subjects(name)),
            attendance(status),
            fee_balances(*)
        """).eq("id", sid).eq("results.term", term).eq("fee_balances.term", term).single().execute()

        d = details.data or {}
        
        # Results processing
        subj_scores = {}
        for r in (d.get("results") or []):
            subj = r["subjects"]["name"]
            subj_scores.setdefault(subj, []).append(r["score"])
        results_clean = {subj: round(sum(sc)/len(sc), 2) for subj, sc in subj_scores.items()}

        # Attendance processing
        att_list = d.get("attendance") or []
        present = sum(1 for a in att_list if a["status"].lower() == "present")
        att_pct = round((present / len(att_list)) * 100, 1) if att_list else 0

        # Fees
        fee = d.get("fee_balances")[0] if d.get("fee_balances") else {"balance": 0, "cleared": False}

        return {
            "name": student.data["name"],
            "admission_number": student.data["admission_number"],
            "class": student.data["classes"]["name"] if student.data.get("classes") else "N/A",
            "results": results_clean,
            "attendance_pct": att_pct,
            "fee_balance": fee["balance"],
            "fee_cleared": fee["cleared"],
        }

    elif tool_name == "get_attendance_summary":
        class_id = parameters.get("class_id")
        
        # Optimized: Single aggregation query would be better, but Supabase client prefers simple filters.
        # Still, we avoid fetching all student IDs first if we don't need to.
        query = db.table("attendance").select("status, students!inner(school_id, class_id)")
        query = query.eq("students.school_id", school_id)
        if class_id:
            query = query.eq("students.class_id", class_id)
        
        records = query.execute().data or []
        summary = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
        for r in records:
            s = r["status"].lower()
            if s in summary:
                summary[s] += 1
        total = len(records)
        pct = round((summary["present"] / total) * 100, 1) if total > 0 else 0
        return {"attendance_summary": summary, "attendance_pct": pct, "total_days": total}

    elif tool_name == "get_class_ranking":
        term = parameters.get("term", "Term 1 2025")
        # Optimized: Fetch results grouped by class in a more efficient way if possible,
        # but let's stick to a clean two-step batch fetch to keep logic simple.
        classes = db.table("classes").select("id, name").eq("school_id", school_id).execute().data or []
        if not classes: return {"class_ranking": []}
        
        c_ids = [c["id"] for c in classes]
        all_results = db.table("results").select("score, class_id").in_("class_id", c_ids).eq("term", term).execute().data or []
        
        class_scores = {}
        for r in all_results:
            class_scores.setdefault(r["class_id"], []).append(r["score"])
            
        ranking = []
        for c in classes:
            scores = class_scores.get(c["id"], [])
            mean = round(sum(scores) / len(scores), 2) if scores else 0
            ranking.append({"class_name": c["name"], "mean_score": mean})

        ranking.sort(key=lambda x: x["mean_score"], reverse=True)
        for i, r in enumerate(ranking):
            r["rank"] = i + 1
        return {"class_ranking": ranking}

    elif tool_name == "get_teacher_performance":
        # Headteacher‑only tool
        if role != "headteacher":
            return {"error": "Only the headteacher can view teacher performance"}

        from app.services.teacher_analytics_service import compute_teacher_value_add
        term = parameters.get("term", "Term 1 2025")
        prev = parameters.get("previous_term")
        teachers = compute_teacher_value_add(school_id, term, prev)
        # Remove sensitive codes – only return name and stats
        clean = []
        for t in teachers:
            clean.append({
                "teacher_name": t["teacher_name"],
                "current_mean": t["current_mean"],
                "change": t.get("change"),
                "value_add": t.get("value_add"),
                "risk_student_count": t.get("risk_student_count"),
            })
        return {"teachers": clean}

    elif tool_name == "search_students":
        query = parameters.get("query", "")
        if not query:
            return {"students": []}
        
        # Search by admission number or name
        res = db.table("students").select("id, name, admission_number, class_id").eq("school_id", school_id).or_(f"admission_number.eq.{query},name.ilike.%{query}%").limit(10).execute()
        
        students = []
        for s in res.data or []:
            students.append({
                "id": s["id"],
                "name": s["name"],
                "admission_number": s["admission_number"],
                "class_name": class_name(s["class_id"])
            })
        return {"students": students}

    else:
        return {"error": f"Unknown tool: {tool_name}"}
