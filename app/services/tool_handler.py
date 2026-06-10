"""
Secure tool handler for Ar‑Learn AI Assistant.
All tools are READ‑ONLY, scoped to the user's school, and never expose credentials.
"""

from app.core.database import get_supabase
from typing import Optional


def execute_tool(tool_name: str, parameters: dict, context: dict) -> dict:
    """
    Execute a safe read‑only tool.
    context must contain: school_id, role, teacher_id (optional)
    """
    db = get_supabase()
    school_id = context["school_id"]
    role = context.get("role", "teacher")

    # ── Safe lookup helpers ──

    def student_name(sid: str) -> str:
        s = db.table("students").select("name").eq("id", sid).single().execute()
        return s.data["name"] if s.data else sid

    def subject_name(sid: str) -> str:
        s = db.table("subjects").select("name").eq("id", sid).single().execute()
        return s.data["name"] if s.data else sid

    def class_name(cid: str) -> str:
        c = db.table("classes").select("name").eq("id", cid).single().execute()
        return c.data["name"] if c.data else cid

    # ── Tool implementations ──

    if tool_name == "get_school_overview":
        from app.services.analytics_service import get_school_overview
        return get_school_overview(school_id)

    elif tool_name == "get_top_students":
        class_id = parameters.get("class_id")
        subject_id = parameters.get("subject_id")
        limit = min(int(parameters.get("limit", 5)), 20)

        query = db.table("results").select("student_id, score").eq("term", parameters.get("term", "Term 1 2025"))
        if class_id:
            query = query.eq("class_id", class_id)
        if subject_id:
            query = query.eq("subject_id", subject_id)
        results = query.execute().data or []

        # Average per student
        scores = {}
        for r in results:
            scores.setdefault(r["student_id"], []).append(r["score"])
        avg = [(sid, sum(sc)/len(sc)) for sid, sc in scores.items()]
        avg.sort(key=lambda x: x[1], reverse=True)

        top = []
        for sid, mean in avg[:limit]:
            s = db.table("students").select("name, class_id").eq("id", sid).eq("school_id", school_id).single().execute()
            if s.data:
                top.append({
                    "student_name": s.data["name"],
                    "class_name": class_name(s.data["class_id"]),
                    "mean_score": round(mean, 2),
                })
        return {"top_students": top}

    elif tool_name == "get_student_profile":
        student_name = parameters.get("student_name")
        admission = parameters.get("admission_number")
        if not student_name and not admission:
            return {"error": "Provide student_name or admission_number"}

        query = db.table("students").select("id, name, class_id, admission_number").eq("school_id", school_id)
        if admission:
            query = query.eq("admission_number", admission)
        else:
            query = query.ilike("name", f"%{student_name}%")
        student = query.limit(1).single().execute()

        if not student.data:
            return {"error": "Student not found"}

        sid = student.data["id"]
        term = parameters.get("term", "Term 1 2025")

        # Results
        results = db.table("results").select("subject_id, score").eq("student_id", sid).eq("term", term).execute().data or []
        subj_scores = {}
        for r in results:
            subj = subject_name(r["subject_id"])
            subj_scores.setdefault(subj, []).append(r["score"])
        results_clean = {subj: round(sum(sc)/len(sc), 2) for subj, sc in subj_scores.items()}

        # Attendance
        attendance = db.table("attendance").select("status").eq("student_id", sid).execute().data or []
        present = sum(1 for a in attendance if a["status"] == "Present")
        total = len(attendance)
        att_pct = round((present / total) * 100, 1) if total > 0 else 0

        # Fees
        fee = db.table("fee_balances").select("balance, cleared").eq("student_id", sid).eq("term", term).maybe_single().execute()
        fee_balance = fee.data["balance"] if fee.data else 0
        fee_cleared = fee.data["cleared"] if fee.data else False

        return {
            "name": student.data["name"],
            "admission_number": student.data["admission_number"],
            "class": class_name(student.data["class_id"]),
            "results": results_clean,
            "attendance_pct": att_pct,
            "fee_balance": fee_balance,
            "fee_cleared": fee_cleared,
        }

    elif tool_name == "get_attendance_summary":
        class_id = parameters.get("class_id")
        if class_id:
            students = db.table("students").select("id").eq("class_id", class_id).eq("school_id", school_id).execute().data
        else:
            students = db.table("students").select("id").eq("school_id", school_id).execute().data
        sids = [s["id"] for s in students] if students else []

        records = db.table("attendance").select("status").in_("student_id", sids).execute().data or []
        summary = {"present": 0, "absent": 0, "sick": 0, "suspended": 0}
        for r in records:
            s = r["status"].lower()
            if s in summary:
                summary[s] += 1
        total = sum(summary.values())
        pct = round((summary["present"] / total) * 100, 1) if total > 0 else 0
        return {"attendance_summary": summary, "attendance_pct": pct, "total_days": total}

    elif tool_name == "get_fee_summary":
        students = db.table("students").select("id").eq("school_id", school_id).execute().data
        sids = [s["id"] for s in students] if students else []
        if not sids:
            return {"total_outstanding": 0, "cleared_count": 0}
        balances = db.table("fee_balances").select("balance, cleared").in_("student_id", sids).eq("term", parameters.get("term", "Term 1 2025")).execute().data or []
        outstanding = sum(b["balance"] for b in balances)
        cleared = sum(1 for b in balances if b["cleared"])
        return {"total_outstanding": outstanding, "cleared_count": cleared}

    elif tool_name == "get_class_ranking":
        classes = db.table("classes").select("id, name").eq("school_id", school_id).execute().data or []
        term = parameters.get("term", "Term 1 2025")
        ranking = []
        for c in classes:
            students = db.table("students").select("id").eq("class_id", c["id"]).execute().data
            cids = [s["id"] for s in students]
            results = db.table("results").select("score").in_("student_id", cids).eq("term", term).execute().data or []
            mean = round(sum(r["score"] for r in results) / len(results), 2) if results else 0
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
