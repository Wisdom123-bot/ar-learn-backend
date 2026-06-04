from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.core.database import get_supabase
from app.schemas.ai_assistant import AIQueryRequest, AIQueryResponse
from app.services.ai_assistant_service import answer_question   # rule‑based fallback
from app.services.llm_client import ask_llm
from app.services.tool_handler import execute_tool
import json
import re

router = APIRouter(prefix="/ai-assistant", tags=["AI Assistant"])

security = HTTPBearer(auto_error=False)

TOOLS = [
    {
        "name": "get_school_overview",
        "description": "Get overall school performance including mean score, best/worst class and subject.",
        "parameters": {}
    },
    {
        "name": "get_top_students",
        "description": "Get top performing students overall or in a specific class/subject.",
        "parameters": {
            "class_id": {"type": "string", "description": "Optional class UUID"},
            "subject_id": {"type": "string", "description": "Optional subject UUID"},
            "term": {"type": "string", "description": "Term, e.g. 'Term 1 2025'"},
            "limit": {"type": "integer", "description": "Number of students, max 20"}
        }
    },
    {
        "name": "get_student_profile",
        "description": "Get a student's results, attendance, and fee status.",
        "parameters": {
            "student_name": {"type": "string", "description": "Student's full name or part of it"},
            "admission_number": {"type": "string", "description": "Student admission number"},
            "term": {"type": "string", "description": "Term, e.g. 'Term 1 2025'"}
        }
    },
    {
        "name": "get_attendance_summary",
        "description": "Get attendance summary for a class or the whole school.",
        "parameters": {
            "class_id": {"type": "string", "description": "Optional class UUID"}
        }
    },
    {
        "name": "get_fee_summary",
        "description": "Get total outstanding fees and number of cleared students.",
        "parameters": {
            "term": {"type": "string", "description": "Term, e.g. 'Term 1 2025'"}
        }
    },
    {
        "name": "get_class_ranking",
        "description": "Get all classes ranked by mean score.",
        "parameters": {
            "term": {"type": "string", "description": "Term, e.g. 'Term 1 2025'"}
        }
    },
    {
        "name": "get_teacher_performance",
        "description": "Get teacher value-add scores. Only available for headteachers.",
        "parameters": {
            "term": {"type": "string", "description": "Current term, e.g. 'Term 1 2025'"},
            "previous_term": {"type": "string", "description": "Previous term for comparison, e.g. 'Term 3 2024'"}
        }
    }
]

# Relaxed system prompt – allows natural answers or tool calls
SYSTEM_PROMPT = (
    "You are Ar‑Learn, a helpful assistant for a Kenyan school. "
    "You can answer general questions about the school using natural language, "
    "or you can fetch specific data using the provided tools. "
    "If the user asks for information that requires data (like 'best student', 'top class', 'who failed', 'how many paid fees', etc.), "
    "reply ONLY with a JSON object like {\"tool\": \"<tool_name>\", \"parameters\": { ... }}. "
    "For all other questions (e.g., 'hello', 'how are you', 'what is chemistry'), answer in plain English. "
    "You MUST NOT include any extra text when returning JSON. "
    "Never ask for credentials or sensitive codes."
)

GUEST_SYSTEM_PROMPT = (
    "You are Ar‑Learn, a school management platform assistant. "
    "The user is NOT logged in. Answer only general questions about the platform. "
    "If the user asks for school data, politely tell them to log in."
)


async def get_teacher_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    if credentials is None:
        return None
    db = get_supabase()
    teacher = db.table("teachers").select("*").eq("id", credentials.credentials).single().execute()
    if not teacher.data:
        return None
    return teacher.data


def format_tool_result(tool_name: str, data: dict) -> str:
    if tool_name == "get_top_students":
        students = data.get("top_students", [])
        if not students:
            return "No student results found."
        lines = ["Here are the top students:"]
        for i, s in enumerate(students, 1):
            lines.append(f"{i}. {s['student_name']} ({s['class_name']}) – Mean: {s['mean_score']}%")
        return "\n".join(lines)

    if tool_name == "get_student_profile":
        name = data.get("name", "Student")
        adm = data.get("admission_number", "N/A")
        cls = data.get("class", "N/A")
        att = data.get("attendance_pct", 0)
        fee_cleared = data.get("fee_cleared", False)
        fee_balance = data.get("fee_balance", 0)
        fee_status = "Cleared" if fee_cleared else f"KES {fee_balance:,.2f}"
        return (
            f"📚 {name} ({adm})\n"
            f"Class: {cls}\n"
            f"Attendance: {att}%\n"
            f"Fee: {fee_status}"
        )

    if tool_name == "get_school_overview":
        best_class = data.get("best_class", {}) or {}
        worst_class = data.get("worst_class", {}) or {}
        best_subj = data.get("best_subject", {}) or {}
        worst_subj = data.get("worst_subject", {}) or {}
        return (
            f"🏫 School Mean: {data.get('school_mean', 0)}%\n"
            f"📈 Best Class: {best_class.get('class_name', 'N/A')} ({best_class.get('mean_score', 0)}%)\n"
            f"📉 Worst Class: {worst_class.get('class_name', 'N/A')} ({worst_class.get('mean_score', 0)}%)\n"
            f"🌟 Best Subject: {best_subj.get('subject_name', 'N/A')} ({best_subj.get('mean_score', 0)}%)\n"
            f"⚠️  Weakest Subject: {worst_subj.get('subject_name', 'N/A')} ({worst_subj.get('mean_score', 0)}%)"
        )

    if tool_name == "get_attendance_summary":
        return f"📋 Attendance: {data.get('attendance_pct', 0)}% over {data.get('total_days', 0)} days."

    if tool_name == "get_fee_summary":
        return f"💰 Outstanding Fees: KES {data.get('total_outstanding', 0):,.2f}\n✅ Cleared: {data.get('cleared_count', 0)} students"

    if tool_name == "get_class_ranking":
        ranking = data.get("class_ranking", [])
        if not ranking:
            return "No class ranking data."
        lines = ["📊 Class Rankings:"]
        for r in ranking:
            lines.append(f"{r['rank']}. {r['class_name']} – {r['mean_score']}%")
        return "\n".join(lines)

    if tool_name == "get_teacher_performance":
        teachers = data.get("teachers", [])
        if not teachers:
            return "No teacher performance data."
        lines = ["👩‍🏫 Teacher Performance:"]
        for t in teachers:
            lines.append(f"• {t['teacher_name']} – Mean: {t['current_mean']}%, Value‑Add: {t.get('value_add', 'N/A')}")
        return "\n".join(lines)

    return json.dumps(data, indent=2)


# Very simple keyword‑based fallback when the LLM fails completely
def fallback_tool_call(question: str) -> Optional[dict]:
    q = question.lower()
    if any(w in q for w in ["best student", "top student", "who lead", "who best"]):
        return {"tool": "get_top_students", "parameters": {"limit": 1}}
    if any(w in q for w in ["class rank", "best class", "top class", "worst class"]):
        return {"tool": "get_class_ranking", "parameters": {"term": "Term 1 2025"}}
    if any(w in q for w in ["teacher perf", "teacher value", "value add"]):
        return {"tool": "get_teacher_performance", "parameters": {"term": "Term 1 2025"}}
    if any(w in q for w in ["fee", "paid", "balance", "deficit"]):
        return {"tool": "get_fee_summary", "parameters": {"term": "Term 1 2025"}}
    if any(w in q for w in ["attend", "absent", "present"]):
        return {"tool": "get_attendance_summary", "parameters": {}}
    if any(w in q for w in ["school overview", "school mean", "overall"]):
        return {"tool": "get_school_overview", "parameters": {}}
    return None


@router.post("/ask", response_model=AIQueryResponse)
async def ask_assistant(
    payload: AIQueryRequest,
    request: Request,
    teacher: Optional[dict] = Depends(get_teacher_from_token),
):
    db = get_supabase()

    # ----- Guest mode (no token) -----
    if teacher is None:
        llm_response = await ask_llm(payload.question, system=GUEST_SYSTEM_PROMPT)
        if llm_response:
            return AIQueryResponse(answer=llm_response.strip(), related_data={"source": "llm"})
        return AIQueryResponse(
            answer="Ar‑Learn is a school management and analytics platform for Kenyan schools. "
                   "It helps with results, CBC assessments, attendance, fees, and more. "
                   "Log in to ask specific questions about your school!",
            related_data={"source": "fallback"}
        )

    # ----- Authenticated mode -----
    if teacher["school_id"] != payload.school_id:
        raise HTTPException(status_code=403, detail="Access denied: wrong school")

    school = db.table("schools").select("id").eq("id", payload.school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    context = {
        "school_id": payload.school_id,
        "role": teacher["role"],
        "teacher_id": teacher["id"],
    }

    # 1. Ask the LLM (Llama → Gemini → Groq)
    full_prompt = (
        f"Available tools: {json.dumps(TOOLS)}\n\n"
        f"User question: \"{payload.question}\"\n\n"
        "Reply with a JSON tool call or a natural language answer."
    )

    llm_response = await ask_llm(full_prompt, system=SYSTEM_PROMPT)

    # 2. Try to extract a JSON tool call from the response
    if llm_response:
        clean = llm_response.strip()
        # Remove possible markdown code fences
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.endswith("```"):
            clean = clean[:-3]
        try:
            tool_call = json.loads(clean)
            if "tool" in tool_call and "parameters" in tool_call:
                result = execute_tool(tool_call["tool"], tool_call["parameters"], context)
                return AIQueryResponse(
                    answer=format_tool_result(tool_call["tool"], result),
                    related_data={"source": "tool", "tool_used": tool_call["tool"]}
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # 3. If the LLM returned a plain English answer, use it
    if llm_response and len(llm_response) > 5 and not llm_response.startswith("{"):
        return AIQueryResponse(answer=llm_response.strip(), related_data={"source": "llm"})

    # 4. Last resort: keyword‑based fallback (still secure, read‑only)
    fb = fallback_tool_call(payload.question)
    if fb:
        result = execute_tool(fb["tool"], fb["parameters"], context)
        return AIQueryResponse(
            answer=format_tool_result(fb["tool"], result),
            related_data={"source": "keyword"}
        )

    # 5. Ultimate fallback: rule‑based assistant
    fallback = answer_question(payload.school_id, payload.question)
    return AIQueryResponse(answer=fallback["answer"], related_data=fallback["related_data"])