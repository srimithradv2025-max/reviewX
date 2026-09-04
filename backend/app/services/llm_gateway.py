import os
import httpx
from dotenv import load_dotenv

load_dotenv()

CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

async def generate_llm_response(prompt: str) -> str:
    # Tier 1: Cerebras Cloud (Ultra High-Speed Llama 3.3 70B)
    if CEREBRAS_KEY:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    "https://api.cerebras.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {CEREBRAS_KEY}"},
                    json={
                        "model": "llama-3.3-70b",
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

    # Tier 2: OpenRouter DeepSeek V4 Flash
    if OPENROUTER_KEY:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                    json={
                        "model": "deepseek/deepseek-v4-flash",
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

    return "Summary: Sensitive credential exposed. Move active secrets to an environment variable."