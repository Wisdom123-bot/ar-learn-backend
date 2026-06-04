from fastapi import APIRouter, HTTPException
from app.core.database import get_supabase
from app.schemas.ai_assistant import AIQueryRequest, AIQueryResponse
from app.services.ai_assistant_service import answer_question   # rule‑based fallback
from app.services.llm_client import ask_llm

router = APIRouter(prefix="/ai-assistant", tags=["AI Assistant"])

SYSTEM_PROMPT = (
    "You are Ar‑Learn, a helpful assistant for Kenyan schools. "
    "You have access to real‑time analytics, student data, teacher performance, "
    "attendance, fees, and CBC competency results. "
    "Answer questions clearly and provide actionable insights. "
    "If you need specific data to answer, explain what you would look up."
)


@router.post("/ask", response_model=AIQueryResponse)
async def ask_assistant(payload: AIQueryRequest):
    db = get_supabase()
    # Verify school exists
    school = db.table("schools").select("id").eq("id", payload.school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    # 1. Try the LLM first (Llama 3.2 1B)
    llm_answer = await ask_llm(payload.question, system=SYSTEM_PROMPT)
    if llm_answer:
        # LLM responded successfully – return its answer
        return AIQueryResponse(
            answer=llm_answer.strip(),
            related_data={"source": "llm"}
        )

    # 2. Fallback to rule‑based assistant
    result = answer_question(payload.school_id, payload.question)
    return AIQueryResponse(answer=result["answer"], related_data=result["related_data"])