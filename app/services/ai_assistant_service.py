import re
from app.services.analytics_service import get_school_overview, get_class_analytics
from app.core.database import get_supabase


def answer_question(school_id: str, question: str) -> dict:
    """
    Parse a natural‑language question about school performance,
    fetch relevant analytics, and return an answer + supporting data.
    """
    question_lower = question.lower()
    db = get_supabase()

    # 1. Detect intent: class performance decline
    class_decline_pattern = r"why did (grade|class) (\d+|\w+) perform (poorly|badly|worse)"
    match = re.search(class_decline_pattern, question_lower)
    if match:
        grade_name = match.group(2)  # e.g., "8" or "orange"
        # Find class by name containing the grade number
        classes = (
            db.table("classes")
            .select("id, name")
            .eq("school_id", school_id)
            .like("name", f"%{grade_name}%")
            .execute()
            .data
        )
        if not classes:
            return {"answer": f"No class matching 'Grade {grade_name}' found in this school.", "related_data": {}}

        class_id = classes[0]["id"]
        analytics = get_class_analytics(class_id)
        # Get school overview for comparison
        school_overview = get_school_overview(school_id)

        class_mean = analytics.get("class_mean", 0)
        school_mean = school_overview.get("school_mean", 0)
        diff = school_mean - class_mean if school_mean else 0

        answer_parts = [
            f"{classes[0]['name']} has a mean score of {class_mean:.1f}%.",
        ]
        if diff > 0:
            answer_parts.append(f"It is {diff:.1f}% below the school average of {school_mean:.1f}%.")
        # Find weakest subjects in class
        weakest = min(analytics.get("students", []), key=lambda x: x.get("mean_score", 0), default=None)
        if weakest:
            answer_parts.append(f"The lowest performing student is {weakest['name']} with a mean of {weakest['mean_score']:.1f}%.")
        # Suggest worst subjects from school overview
        worst_subject = school_overview.get("worst_subject")
        if worst_subject:
            answer_parts.append(f"The school's weakest subject overall is {worst_subject['subject_name']} ({worst_subject['mean_score']:.1f}%), which may also affect this class.")

        return {
            "answer": " ".join(answer_parts),
            "related_data": {
                "class_analytics": analytics,
                "school_overview": school_overview,
            },
        }

    # 2. Intent: best/worst performing class
    if "best class" in question_lower or "top class" in question_lower:
        overview = get_school_overview(school_id)
        best = overview.get("best_class")
        if best:
            return {"answer": f"The best performing class is {best['class_name']} with a mean of {best['mean_score']:.2f}%.", "related_data": {"best_class": best}}
        return {"answer": "No performance data available yet.", "related_data": {}}

    if "worst class" in question_lower:
        overview = get_school_overview(school_id)
        worst = overview.get("worst_class")
        if worst:
            return {"answer": f"The lowest performing class is {worst['class_name']} with a mean of {worst['mean_score']:.2f}%.", "related_data": {"worst_class": worst}}
        return {"answer": "No performance data available yet.", "related_data": {}}

    # 3. Intent: best/worst subject
    if "best subject" in question_lower:
        overview = get_school_overview(school_id)
        best_sub = overview.get("best_subject")
        if best_sub:
            return {"answer": f"The best performing subject is {best_sub['subject_name']} with a mean of {best_sub['mean_score']:.2f}%.", "related_data": {"best_subject": best_sub}}
        return {"answer": "No subject data available.", "related_data": {}}

    if "worst subject" in question_lower:
        overview = get_school_overview(school_id)
        worst_sub = overview.get("worst_subject")
        if worst_sub:
            return {"answer": f"The subject needing most attention is {worst_sub['subject_name']} with a mean of {worst_sub['mean_score']:.2f}%.", "related_data": {"worst_subject": worst_sub}}
        return {"answer": "No subject data available.", "related_data": {}}

    # 4. Intent: school mean score
    if "school mean" in question_lower or "overall mean" in question_lower:
        overview = get_school_overview(school_id)
        mean = overview.get("school_mean", 0)
        return {"answer": f"The overall school mean score is {mean:.2f}%.", "related_data": {"school_overview": overview}}

    # 5. Fallback: generic assistance
    return {
        "answer": (
            "I can help you with questions like:\n"
            "- Why did Grade X perform poorly?\n"
            "- Which is the best class?\n"
            "- Which subject needs improvement?\n"
            "- What is the school mean score?\n"
            "Please try rephrasing your question."
        ),
        "related_data": {},
    }