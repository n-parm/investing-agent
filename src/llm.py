import json
import requests
from typing import Dict
from .config import OLLAMA_MODEL

def build_prompt(text: str) -> list:
    system = {
        "role": "system",
        "content": (
            "You MUST respond with valid JSON only matching the schema:"
            "{\n  \"summary_bullets\": [string],\n  \"event_type\": string,"
            "\n  \"impact_level\": string,\n  \"impact_reasoning\": string\n}\n"
        ),
    }
    user = {"role": "user", "content": text}
    return [system, user]

def analyze_filing(text: str, model: str = OLLAMA_MODEL, temperature: float = 0.25) -> Dict:
    """
    Attempts to call a local Ollama API. This is a best-effort wrapper; in case the server
    is not available the function will raise a RuntimeError with a helpful message.
    """
    # Try Ollama HTTP endpoint (best-effort). If your local setup uses different endpoint,
    # adapt accordingly.
    try:
        url = f"http://localhost:11434/api/chat"
        payload = {
            "model": model,
            "messages": build_prompt(text),
            "temperature": temperature,
        }
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        # Expect data to contain a top-level `choices`/message structure. Attempt to extract text.
        # This is intentionally forgiving — adapt to your Ollama output shape.
        content = None
        if isinstance(data, dict):
            # common structure
            if "choices" in data and data["choices"]:
                content = data["choices"][0].get("message", {}).get("content")
            elif "message" in data:
                content = data["message"].get("content")
            else:
                # fallback: maybe the API echoes as 'text'
                content = data.get("text")

        if not content:
            raise RuntimeError(f"LLM returned unexpected payload: {data}")

        # enforce JSON-only response per prompt
        return json.loads(content)
    except Exception as exc:
        raise RuntimeError(
            "LLM analysis failed — ensure Ollama is running and reachable at http://localhost:11434/api/chat. "
            f"Error: {exc}"
        )
