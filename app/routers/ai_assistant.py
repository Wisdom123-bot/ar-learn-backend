from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from app.core.database import get_supabase
from app.schemas.ai_assistant import AIQueryRequest, AIQueryResponse
from app.services.ai_assistant_service import answer_question   # rule‑based fallback
from app.services.llm_client import ask_llm
from app.services.tool_handler import execute_tool
import json

router = APIRouter(prefix="/ai-assistant", tags=["AI Assistant"])

security = HTTPBearer(auto_error=False)   # token is optional for guests

# Actual tool definitions
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

SYSTEM_PROMPT = (
    "You are Ar‑Learn, an AI assistant for a Kenyan school. "
    "You can answer general questions and use tools to fetch real school data. "
    "When a user asks for specific information about their school (students, results, attendance, fees, teacher performance), "
    "respond ONLY with a JSON object containing 'tool' (the tool name) and 'parameters' (a dict). "
    "Do not add any extra text. If the question is general knowledge, answer normally. "
    "Never ask for credentials or sensitive codes."
)

GUEST_SYSTEM_PROMPT = (
    "You are Ar‑Learn, an AI assistant for a school management platform. "
    "The user is NOT logged in. Answer only general questions about the platform: "
    "what it does, its features, who it helps, how to get started, etc. "
    "If the user asks for specific school data (results, attendance, fees, students), "
    "politely explain that they need to log in first. "
    "Keep answers friendly, helpful, and brief."
)


async def get_teacher_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    If a valid token is provided, return the teacher record.
    If no token or invalid, return None (guest user).
    """
    if credentials is None:
        return None
    db = get_supabase()
    teacher = db.table("teachers").select("*").eq("id", credentials.credentials).single().execute()
    if not teacher.data:
        return None
    return teacher.data


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

    full_prompt = (
        f"Available tools: {json.dumps(TOOLS)}\n\n"
        f"User question: {payload.question}\n\n"
        "Respond with JSON if you need a tool, otherwise answer normally."
    )

    llm_response = await ask_llm(full_prompt, system=SYSTEM_PROMPT)

    # Try to parse JSON (tool call)
    try:
        tool_call = json.loads(llm_response.strip())
        if "tool" in tool_call and "parameters" in tool_call:
            result = execute_tool(tool_call["tool"], tool_call["parameters"], context)
            final_answer = await ask_llm(
                f"Data: {json.dumps(result)}\n\nUser question: {payload.question}\n\nGive a short, friendly answer.",
                system="You are a helpful school assistant. Use the data provided to answer the user's question clearly."
            )
            if final_answer:
                return AIQueryResponse(answer=final_answer.strip(), related_data={"source": "llm+tool", "tool_used": tool_call["tool"]})
            return AIQueryResponse(answer=json.dumps(result), related_data={"source": "tool", "tool_used": tool_call["tool"]})
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    if llm_response:
        return AIQueryResponse(answer=llm_response.strip(), related_data={"source": "llm"})

    # Fallback to rule‑based
    fallback = answer_question(payload.school_id, payload.question)
    return AIQueryResponse(answer=fallback["answer"], related_data=fallback["related_data"])