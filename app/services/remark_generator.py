from typing import List, Dict, Optional

# ============================================================
# RULE-BASED REMARK GENERATOR (Phase 1 AI)
# ============================================================

def generate_professional_remark(
    student_name: str,
    subject_name: str,
    score: float,
    previous_score: Optional[float] = None,
    teacher_remark: str = ""
) -> str:
    """
    Transforms basic teacher remarks into detailed, professional feedback.
    Uses score thresholds and simple trend analysis.
    """
    # Determine performance level
    if score >= 80:
        level = "excellent"
    elif score >= 60:
        level = "good"
    elif score >= 40:
        level = "average"
    else:
        level = "below average"

    # Build base remark from teacher input, or generate fully
    if teacher_remark and len(teacher_remark) > 5:
        base = teacher_remark
    else:
        # Auto‑generate a bare remark if teacher left it empty
        templates = {
            "excellent": f"{student_name} demonstrates outstanding understanding in {subject_name}.",
            "good": f"{student_name} shows consistent effort in {subject_name}.",
            "average": f"{student_name} is making steady progress in {subject_name}.",
            "below average": f"{student_name} requires additional support in {subject_name}.",
        }
        base = templates[level]

    # Add trend observation if previous score available
    trend = ""
    if previous_score is not None:
        diff = score - previous_score
        if diff >= 10:
            trend = f" This is a significant improvement of {diff:.1f}% from the previous assessment."
        elif diff >= 3:
            trend = f" An improvement of {diff:.1f}% was observed."
        elif diff <= -10:
            trend = f" However, there was a notable decline of {abs(diff):.1f}% compared to the previous result."
        elif diff <= -3:
            trend = f" A slight drop of {abs(diff):.1f}% was recorded."

    # Add recommendation based on level
    recommendations = {
        "excellent": " Continue to challenge with advanced material to sustain excellence.",
        "good": " Focus on turning consistent good performance into excellent results through targeted practice.",
        "average": " Additional practice on core concepts can help move performance to the next level.",
        "below average": " Remedial sessions focusing on fundamentals are strongly recommended.",
    }

    return base + trend + recommendations[level]


# ============================================================
# INTERVENTION DETECTOR
# ============================================================

def detect_risk_flags(
    student_id: str,
    current_results: List[Dict],    # list of {"subject": str, "score": float}
    previous_results: List[Dict] = None,
    attendance_pct: Optional[float] = None
) -> List[str]:
    """
    Returns a list of human‑readable risk flags for a student.
    Current_results must be a list of dicts with keys: subject_name, score.
    Previous_results is optional for trend detection.
    """
    flags = []

    # 1. Failing or near‑failing any subject (score < 40)
    for r in current_results:
        if r["score"] < 40:
            flags.append(f"Likely to fail {r['subject_name']} (current score: {r['score']}%)")

    # 2. Major performance drop (if previous data available)
    if previous_results:
        prev_map = {p["subject_name"]: p["score"] for p in previous_results}
        for r in current_results:
            prev = prev_map.get(r["subject_name"])
            if prev is not None and (prev - r["score"]) >= 20:
                flags.append(
                    f"Performance in {r['subject_name']} dropped by {prev - r['score']:.0f}% (from {prev}% to {r['score']}%)"
                )

    # 3. Attendance concern
    if attendance_pct is not None and attendance_pct < 75:
        flags.append(f"Attended only {attendance_pct:.0f}% of lessons this term – attendance risk")

    # 4. Overall weak trend (average below 50)
    if current_results:
        avg = sum(r["score"] for r in current_results) / len(current_results)
        if avg < 50:
            # Find weakest subject
            weakest = min(current_results, key=lambda x: x["score"])
            flags.append(
                f"Overall mean ({avg:.1f}%) is below 50%. Weakest area: {weakest['subject_name']} "
                f"({weakest['score']}%). Recommend remedial focus on {weakest['subject_name']}."
            )

    return flags


# ============================================================
# EXAMPLE USAGE (run this file directly to test)
# ============================================================
if __name__ == "__main__":
    remark = generate_professional_remark("John", "Mathematics", 72, previous_score=58, teacher_remark="")
    print("Generated Remark:", remark)

    flags = detect_risk_flags(
        "student-uuid",
        current_results=[
            {"subject_name": "Mathematics", "score": 34},
            {"subject_name": "English", "score": 68},
        ],
        previous_results=[
            {"subject_name": "Mathematics", "score": 62},
            {"subject_name": "English", "score": 70},
        ],
        attendance_pct=68,
    )
    for flag in flags:
        print("Risk Flag:", flag)