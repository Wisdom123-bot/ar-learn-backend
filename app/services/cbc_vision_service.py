import base64
import json
import re
import httpx
import os
from typing import Dict
from app.services.llm_client import GEMINI_KEY

GEMINI_VISION_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

async def analyze_cbc_project(image_base64: str) -> Dict:
    """
    Uses Gemini 1.5 Flash Vision capabilities to analyze a student project.
    This model supports native multimodal (image + text) input.
    """
    if not GEMINI_KEY:
        # Fallback to simulated response if no key
        return {
            "competency": "Creativity & Imagination",
            "level": "ME",
            "remark": "The project demonstrates a good grasp of the concepts with clear personal expression (Simulated)."
        }

    prompt = (
        "Analyze this Kenyan CBC student project image. "
        "1. Identify the core competency (e.g. Creativity, Communication, Collaboration). "
        "2. Suggest an assessment level: EE (Exceeding Expectations), ME (Meeting Expectations), "
        "AE (Approaching Expectations), or BE (Below Expectations). "
        "3. Provide a brief professional remark for the report card. "
        "Output JSON only: {\"competency\": \"...\", \"level\": \"...\", \"remark\": \"...\"}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "topK": 32,
            "topP": 1,
            "maxOutputTokens": 1024,
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GEMINI_VISION_URL}?key={GEMINI_KEY}",
                json=payload,
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            
            text_response = data["candidates"][0]["content"]["parts"][0]["text"]
            
            # Extract JSON from the response text
            match = re.search(r'\{.*\}', text_response, re.DOTALL)
            if match:
                return json.loads(match.group())
                
    except Exception as e:
        print(f"Gemini Vision Error: {str(e)}")
        
    # Default Fallback
    return {
        "competency": "Creativity & Imagination",
        "level": "ME",
        "remark": "The project demonstrates a good grasp of the concepts with clear personal expression."
    }
