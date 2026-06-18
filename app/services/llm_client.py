import httpx
import os
import json
import asyncio
from typing import AsyncGenerator

# Reduced Timeouts for snappiness (seconds)
TIMEOUT_LLAMA   = 10
TIMEOUT_GEMINI  = 12
TIMEOUT_GROQ    = 10

# URLs
LLAMA_URL = os.getenv("LLM_SERVER_URL", "https://arlearn-arlearn.hf.space/generate")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Keys
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_KEY = os.getenv("GROQ_API_KEY", "")


async def ask_llm(prompt: str, system: str = "", stream: bool = False):
    """
    Poll multiple LLM providers. If stream is True, returns an AsyncGenerator.
    """
    if stream:
        return _stream_groq(prompt, system)

    tasks = [
        _call_llama(prompt, system),
        _call_gemini(prompt, system),
        _call_groq(prompt, system)
    ]

    for coro in asyncio.as_completed(tasks):
        try:
            answer = await coro
            if answer and answer.strip():
                return answer.strip()
        except Exception:
            continue

    return ""

async def _stream_groq(prompt: str, system: str) -> AsyncGenerator[str, None]:
    if not GROQ_KEY:
        yield "Error: Groq API key missing for streaming."
        return

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": "llama3-70b-8192",
        "messages": messages,
        "temperature": 0.5,
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", GROQ_URL, json=payload, headers=headers, timeout=20.0) as response:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError):
                            continue
    except Exception as e:
        yield f"\n[Streaming Error: {str(e)}]"

# ---------- Individual providers (Non-streaming) ----------

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
        full_text = prompt
        if system:
            full_text = f"System: {system}\n\nUser: {prompt}"
        payload = {
            "contents": [{"parts": [{"text": full_text}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={GEMINI_KEY}",
                json=payload,
                timeout=TIMEOUT_GEMINI,
            )
            resp.raise_for_status()
            data = resp.json()
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
            "max_tokens": 512,
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
