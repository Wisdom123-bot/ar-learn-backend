from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from typing import Optional, AsyncGenerator
from app.core.database import get_supabase
from app.schemas.ai_assistant import AIQueryRequest
from app.services.llm_client import ask_llm
from app.services.tool_handler import execute_tool
from app.dependencies import get_current_user
import json
import re

router = APIRouter(prefix="/ai-assistant", tags=["AI Assistant"])

TOOLS = [
    {"name": "get_school_overview", "description": "Get overall school performance stats."},
    {"name": "get_top_students", "description": "Get top students. Params: class_id, subject_id, term, limit."},
    {"name": "get_student_profile", "description": "Get a student profile. Params: student_name or admission_number, term."},
    {"name": "get_attendance_summary", "description": "Get attendance % for school or class. Params: class_id."},
    {"name": "get_fee_summary", "description": "Get school fee status summary. Params: term."},
    {"name": "get_class_ranking", "description": "Get classes ranked by mean score. Params: term."},
    {"name": "get_teacher_performance", "description": "Headteacher ONLY: Get teacher value-add stats. Params: term."},
    {"name": "search_students", "description": "Search for students by name/number to get IDs. Params: query."}
]

SYSTEM_PROMPT = (
    "You are Ar‑Learn AI, a helpful Kenyan school assistant. "
    "You have tools to fetch real data. Always prefer tools for specific data queries. "
    "\n\nTOOL USE FORMAT:"
    "\nIf you need data, output a single JSON object: {\"tool\": \"tool_name\", \"parameters\": {...}}."
    "\nYou can use tools multiple times if needed to answer a complex question. "
    "\n\nWhen you have the data, explain it naturally to the user. "
    "\nRole Context: {role}, School ID: {school_id}"
)

def extract_json(text: str) -> Optional[dict]:
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except: pass
    return None

async def assistant_streamer(question: str, context: dict) -> AsyncGenerator[str, None]:
    """
    Multi-step reasoning (ReAct) streamer.
    """
    role = context["role"]
    school_id = context["school_id"]
    
    current_prompt = f"User Question: {question}"
    history = []
    
    # Max 3 reasoning steps
    for _ in range(3):
        # 1. Ask LLM for next action
        full_system = SYSTEM_PROMPT.format(role=role, school_id=school_id)
        if history:
            full_system += "\n\nPrevious Tool Results:\n" + "\n".join(history)
            
        llm_response = await ask_llm(current_prompt, system=full_system, stream=False)
        
        if not llm_response:
            yield "I'm sorry, I'm having trouble connecting to my brain right now."
            return

        tool_call = extract_json(llm_response)
        
        if tool_call and "tool" in tool_call:
            # 2. Execute tool
            tool_name = tool_call["tool"]
            params = tool_call.get("parameters", {})
            yield f"🔍 [Checking {tool_name.replace('_', ' ')}...]\n"
            
            try:
                result = execute_tool(tool_name, params, context)
                history.append(f"Tool {tool_name} returned: {json.dumps(result)}")
                # Loop back to let LLM process the tool result
                continue
            except Exception as e:
                history.append(f"Tool {tool_name} failed: {str(e)}")
                continue
        else:
            # 3. Final answer (No more tools needed)
            # Switch to streaming the final natural response
            async for chunk in await ask_llm(current_prompt, system=full_system + "\n\nProvide the final natural answer based on results.", stream=True):
                yield chunk
            return

    yield "\n[I've reached my thinking limit, but I hope that information helps!]"

@router.post("/ask")
async def ask_assistant(
    payload: AIQueryRequest,
    teacher: dict = Depends(get_current_user),
):
    if teacher["school_id"] != payload.school_id:
        raise HTTPException(status_code=403, detail="Access denied")

    context = {
        "school_id": payload.school_id,
        "role": teacher["role"],
        "teacher_id": teacher["id"],
    }

    return StreamingResponse(
        assistant_streamer(payload.question, context),
        media_type="text/event-stream"
    )
