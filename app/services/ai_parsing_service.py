import json
import re
from typing import List, Dict, Any
from app.services.llm_client import ask_llm

async def parse_students_with_ai(text: str) -> List[Dict[str, Any]]:
    """
    Extracts student names, admission numbers, and grades from text using AI.
    """
    system_prompt = (
        "You are an expert school data parser. Your task is to extract student information from the provided text. "
        "Identify student names, admission numbers (if any), and grades/classes (if any). "
        "Return ONLY a JSON list of objects. Each object should have 'name', 'admission_number', and 'grade' keys. "
        "If a field is missing, use null. Example output: [{\"name\": \"John Doe\", \"admission_number\": \"ADM001\", \"grade\": \"Class 1\"}]"
    )
    
    # Trim text if too long to save tokens/time
    truncated_text = text[:8000]
    
    response = await ask_llm(truncated_text, system=system_prompt)
    
    if not response or not response.strip():
        return []
        
    return _extract_json_from_response(response)

async def parse_results_with_ai(text: str) -> List[Dict[str, Any]]:
    """
    Extracts marks/results from text using AI.
    """
    system_prompt = (
        "You are an expert academic data parser. Your task is to extract student marks from the provided text. "
        "Identify student names or admission numbers and map them to their respective subjects and scores. "
        "Return ONLY a JSON list of objects. Each object should have: "
        "'admission_number', 'name', 'subject', 'score', 'exam_type' (CAT or EXAM), 'term', and 'academic_year'. "
        "If fields like 'term' or 'year' are not explicitly in the row but found in the header, apply them to all rows. "
        "Score must be a number. Use null for missing text fields. "
        "Example output: [{\"admission_number\": \"ADM001\", \"name\": \"John Doe\", \"subject\": \"Math\", \"score\": 85, \"exam_type\": \"EXAM\", \"term\": \"Term 1 2025\", \"academic_year\": \"2025\"}]"
    )
    
    truncated_text = text[:10000]
    
    response = await ask_llm(truncated_text, system=system_prompt)
    
    if not response or not response.strip():
        return []

    return _extract_json_from_response(response)

def _extract_json_from_response(response: str) -> List[Dict[str, Any]]:
    """Helper to find and parse JSON block in LLM response."""
    if not response:
        return []
    
    try:
        # Look for [ ... ] block
        match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        # Fallback to direct load if no markdown
        return json.loads(response)
    except Exception:
        return []
