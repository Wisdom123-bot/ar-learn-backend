import httpx
import os

LLM_SERVER_URL = os.getenv("LLM_SERVER_URL", "https://arlearn-arlearn.hf.space/generate")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "1000"))   # seconds

async def ask_llm(prompt: str, system: str = "") -> str:
    """
    Send a prompt to the LLM server and return the answer.
    If the server is unreachable or times out, return an empty string.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                LLM_SERVER_URL,
                json={"prompt": prompt, "system": system},
                timeout=LLM_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
    except Exception:
        return ""   # silent fallback – the rule‑based assistant will take over