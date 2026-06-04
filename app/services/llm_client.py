import httpx
import os
import json

# Timeouts (seconds)
TIMEOUT_LLAMA   =30
TIMEOUT_GEMINI  = 30
TIMEOUT_GROQ    = 30

# URLs
LLAMA_URL = os.getenv("LLM_SERVER_URL", "https://arlearn-arlearn.hf.space/generate")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Keys
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_KEY = os.getenv("GROQ_API_KEY", "")


async def ask_llm(prompt: str, system: str = "") -> str:
    """
    Try Llama first, then Gemini, then Groq.
    Returns the first successful response, or empty string if all fail.
    """
    # 1. Llama (Hugging Face Space)
    answer = await _call_llama(prompt, system)
    if answer:
        return answer

    # 2. Gemini 2.0 Flash
    answer = await _call_gemini(prompt, system)
    if answer:
        return answer

    # 3. Groq (llama3‑8b‑8192 is fast and free)
    answer = await _call_groq(prompt, system)
    if answer:
        return answer

    return ""


# ---------- Individual providers ----------

async def _call_llama(prompt: str, system: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                LLAMA_URL,
                json={"prompt": prompt, "system": system},
                timeout=TIMEOUT_LLAMA,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
    except Exception:
        return ""


async def _call_gemini(prompt: str, system: str) -> str:
    if not GEMINI_KEY:
        return ""
    try:
        # Combine system + prompt into a single user message (Gemini doesn't support separate system in API)
        full_text = prompt
        if system:
            full_text = f"System: {system}\n\nUser: {prompt}"
        payload = {
            "contents": [{"parts": [{"text": full_text}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 256},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={GEMINI_KEY}",
                json=payload,
                timeout=TIMEOUT_GEMINI,
            )
            resp.raise_for_status()
            data = resp.json()
            # Parse Gemini response
            candidates = data.get("candidates", [])
            if candidates and candidates[0].get("content", {}).get("parts"):
                return candidates[0]["content"]["parts"][0].get("text", "")
            return ""
    except Exception:
        return ""


async def _call_groq(prompt: str, system: str) -> str:
    if not GROQ_KEY:
        return ""
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": "llama3-8b-8192",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 300,
        }
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GROQ_URL,
                json=payload,
                headers=headers,
                timeout=TIMEOUT_GROQ,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices and choices[0].get("message", {}).get("content"):
                return choices[0]["message"]["content"]
            return ""
    except Exception:
        return ""