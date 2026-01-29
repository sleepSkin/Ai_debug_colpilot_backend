import os
import httpx

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")  # 你可改成自己本地 `ollama list` 显示的名称
OLLAMA_MODE = os.getenv("OLLAMA_MODE", "chat")       # chat | generate
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))


class OllamaError(RuntimeError):
    pass

def _cfg():
    return {
        "base": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        "model": os.getenv("OLLAMA_MODEL", ""),
        "mode": os.getenv("OLLAMA_MODE", "chat"),
    }

async def call_ollama(prompt: str) -> str:
    """
    Returns raw text response from Ollama.
    """

    cfg = _cfg()
    print("[ollama_client] cfg =", cfg)

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT,trust_env=False) as client:
        if OLLAMA_MODE == "generate":
            url = f"{cfg['base']}/api/generate"
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                # 可选参数：温度低一点更稳
                # "options": {"temperature": 0.2},
            }
            r = await client.post(url, json=payload)

            print("[ollama_client] generate status =", r.status_code)
            print("[ollama_client] generate body =", repr(r.text))
            print("[ollama_client] generate url =", url)
            print("[ollama_client] generate payload keys =", payload.keys())

            if r.status_code >= 400:
                raise OllamaError(f"Ollama generate failed: {r.status_code} {r.text}")
            data = r.json()
            return data.get("response", "")

        # default: chat
        url = f"{OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": "You are a senior debugging assistant. Output JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        r = await client.post(url, json=payload)
        if r.status_code >= 400:
            raise OllamaError(f"Ollama chat failed: {r.status_code} {r.text}")
        data = r.json()
        message = data.get("message") or {}
        return message.get("content", "")
