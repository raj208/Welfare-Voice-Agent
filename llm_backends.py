import os
import requests

OLLAMA_HOST = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")

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

def ollama_chat(messages):
    """
    Tries, in order:
      1) Native Ollama chat: POST /api/chat
      2) OpenAI-compatible: POST /v1/chat/completions
      3) Fallback completion: POST /api/generate
    """
    # 1) Native Ollama /api/chat
    r = _post(
        f"{OLLAMA_HOST}/api/chat",
        {"model": OLLAMA_MODEL, "messages": messages, "stream": False},
    )

    if r.status_code != 404:
        r.raise_for_status()
        data = r.json()
        # Expected native shape: {"message": {"role": "assistant", "content": "..."}}
        return data["message"]["content"]

    # 2) OpenAI compatible /v1/chat/completions
    r2 = _post(
        f"{OLLAMA_HOST}/v1/chat/completions",
        {"model": OLLAMA_MODEL, "messages": messages, "stream": False},
    )
    if r2.ok:
        data = r2.json()
        return data["choices"][0]["message"]["content"]

    # 3) Fallback /api/generate
    prompt = _messages_to_prompt(messages)
    r3 = _post(
        f"{OLLAMA_HOST}/api/generate",
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
    )
    r3.raise_for_status()
    data = r3.json()
    return data["response"]

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
