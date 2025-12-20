import os
import requests

# OLLAMA_HOST = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
# OLLAMA_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")  # ✅ your installed model

def _messages_to_prompt(messages):
    # Convert chat messages to a single prompt for /api/generate fallback
    lines = []
    for m in messages:
        role = m.get("role", "user").upper()
        content = m.get("content", "")
        lines.append(f"{role}: {content}")
    lines.append("ASSISTANT:")
    return "\n".join(lines)

def _post(url, payload, timeout=120):
    return requests.post(url, json=payload, timeout=timeout)


def ollama_chat(messages, model=OLLAMA_MODEL, timeout=120):
    # 1) Ollama native chat
    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("message", {}).get("content", "")
    except Exception:
        pass

    # 2) OpenAI-compatible chat fallback
    r = requests.post(
        f"{OLLAMA_BASE}/v1/chat/completions",
        json={"model": model, "messages": messages, "stream": False},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

def generate_reply(user_text: str, history: list, language_name: str) -> str:
    system_prompt = (
        f"You are a helpful welfare-scheme assistant. "
        f"Always reply ONLY in {language_name}. "
        f"Be concise and ask one follow-up question if you need missing info."
    )

    messages = [{"role": "system", "content": system_prompt}]

    for u, a in history[-6:]:
        messages.append({"role": "user", "content": u})
        messages.append({"role": "assistant", "content": a})

    messages.append({"role": "user", "content": user_text})
    return ollama_chat(messages)
