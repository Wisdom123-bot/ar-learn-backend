from fastapi import APIRouter, HTTPException
from app.core.database import get_supabase
from app.schemas.ai_assistant import AIQueryRequest, AIQueryResponse
from app.services.ai_assistant_service import answer_question

router = APIRouter(prefix="/ai-assistant", tags=["AI Assistant"])


@router.post("/ask", response_model=AIQueryResponse)
async def ask_assistant(payload: AIQueryRequest):
    db = get_supabase()
    # Verify school exists
    school = db.table("schools").select("id").eq("id", payload.school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")

    result = answer_question(payload.school_id, payload.question)
    return AIQueryResponse(answer=result["answer"], related_data=result["related_data"])