import json
import logging
import os
import re
import time
import traceback
from datetime import datetime
import requests
from requests.exceptions import RequestException
from typing import Dict, Optional
from .config import OLLAMA_MODEL, OLLAMA_URL

# Environment-configurable parameters
OLLAMA_CALL_TIMEOUT = int(os.getenv("OLLAMA_CALL_TIMEOUT", "30"))
OLLAMA_CALL_RETRIES = int(os.getenv("OLLAMA_CALL_RETRIES", "3"))
OLLAMA_STREAM_TIMEOUT = int(os.getenv("OLLAMA_STREAM_TIMEOUT", "120"))
DEBUG_DUMP_DIR = os.path.join(os.path.dirname(__file__), "debug_raw")
os.makedirs(DEBUG_DUMP_DIR, exist_ok=True)

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
    # First try a non-streaming request (prefer a complete response). Add
    # a small retry loop and produce clearer logs on failures to help
    # diagnose RemoteDisconnected / connection-abort situations.
    payload = {
        "model": model,
        "messages": build_prompt(text),
        "temperature": temperature,
        "stream": False,
    }

    def _extract_content_from_payload(data) -> str:
        if not isinstance(data, dict):
            return None
        # common structures observed from Ollama
        if "choices" in data and data["choices"]:
            return data["choices"][0].get("message", {}).get("content")
        if "message" in data:
            return data["message"].get("content")
        return data.get("text")

    max_attempts = OLLAMA_CALL_RETRIES
    for attempt in range(1, max_attempts + 1):
        try:
            start = time.perf_counter()
            r = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_CALL_TIMEOUT)
            elapsed = time.perf_counter() - start
            logging.debug("Ollama non-streaming POST time: %.2fs", elapsed)
            # Log status for diagnostics
            logging.debug("Ollama non-streaming POST status: %s", getattr(r, "status_code", None))
            r.raise_for_status()
            try:
                data = r.json()
            except Exception:
                logging.debug("Ollama returned non-JSON body (first 1000 chars): %s", r.text[:1000])
                # Dump raw response for postmortem
                dump_path = os.path.join(DEBUG_DUMP_DIR, f"llm_nonjson_{int(time.time())}.txt")
                try:
                    with open(dump_path, "w", encoding="utf-8") as fh:
                        fh.write(r.text)
                    logging.debug("Wrote non-JSON Ollama response to %s", dump_path)
                except Exception:
                    logging.debug("Failed to write debug dump: %s", traceback.format_exc())
                raise
            content = _extract_content_from_payload(data)
            if content:
                try:
                    return json.loads(content)
                except Exception as e:
                    raise RuntimeError(f"LLM returned non-JSON content: {content} (error: {e})")
            # If no content was returned, break to streaming fallback
            break
        except RequestException as exc_nonstream:
            logging.debug(
                "Attempt %s/%s: non-streaming request failed: %s",
                attempt,
                max_attempts,
                exc_nonstream,
            )
            if attempt < max_attempts:
                time.sleep(1 * attempt)
                continue
            logging.debug("Giving up non-streaming attempts, will try streaming fallback")

    # Streaming fallback: accumulate assistant chunks until done==true
    try:
        payload_stream = {"model": model, "messages": build_prompt(text), "temperature": temperature}
        start = time.perf_counter()
        r = requests.post(OLLAMA_URL, json=payload_stream, stream=True, timeout=OLLAMA_STREAM_TIMEOUT)
        elapsed = time.perf_counter() - start
        logging.debug("Ollama streaming POST time: %.2fs", elapsed)
        logging.debug("Ollama streaming POST status: %s", getattr(r, "status_code", None))
        assembled = ""
        last_chunk = None
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            # Each line should be a small JSON chunk; try to parse it, otherwise append raw
            try:
                chunk = json.loads(line)
            except Exception:
                assembled += line
                last_chunk = line
                continue
            last_chunk = chunk
            msg = chunk.get("message", {}).get("content", "")
            if msg:
                assembled += msg
            if chunk.get("done"):
                break

        if assembled:
            try:
                return json.loads(assembled)
            except Exception as e:
                # Dump assembled content for inspection
                dump_path = os.path.join(DEBUG_DUMP_DIR, f"llm_stream_assembled_{int(time.time())}.txt")
                try:
                    with open(dump_path, "w", encoding="utf-8") as fh:
                        fh.write(assembled)
                    logging.debug("Wrote assembled streamed content to %s", dump_path)
                except Exception:
                    logging.debug("Failed to write assembled dump: %s", traceback.format_exc())
                raise RuntimeError(f"Failed to parse assembled streamed content: {assembled} (error: {e})")

        # If we reach here, no usable assembled content was found
        raise RuntimeError(f"LLM returned no usable content. Last chunk: {last_chunk}")

    except Exception as exc_stream:
        logging.debug("Full stack: %s", traceback.format_exc())
        raise RuntimeError(
            f"LLM analysis failed — ensure Ollama is running and reachable at {OLLAMA_URL}. Error: {exc_stream}"
        )


def check_ollama(timeout: int = 5, model: str = OLLAMA_MODEL) -> dict:
    """Run quick diagnostics against the configured Ollama `OLLAMA_URL`.

    Returns a dict with attempt results for GET and a minimal POST. Useful to
    decide whether to run the project in PowerShell or WSL and to surface
    connection errors like RemoteDisconnected.
    """
    results = {"url": OLLAMA_URL, "get": {}, "post": {}, "ok": False}

    # Try a simple GET (may return 405 but that's still a reachable service)
    try:
        r = requests.get(OLLAMA_URL, timeout=timeout)
        results["get"]["status_code"] = getattr(r, "status_code", None)
        results["get"]["text_snippet"] = (r.text or "")[:2000]
    except Exception as e:
        results["get"]["error"] = repr(e)

    # Try a minimal POST similar to analyze_filing payload (non-streaming)
    payload = {"model": model, "messages": build_prompt("ping"), "temperature": 0.0, "stream": False}
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=max(timeout, 10))
        results["post"]["status_code"] = getattr(r, "status_code", None)
        # capture a short snippet to avoid huge logs
        results["post"]["text_snippet"] = (r.text or "")[:2000]
        if 200 <= results["post"]["status_code"] < 300:
            results["ok"] = True
    except Exception as e:
        results["post"]["error"] = repr(e)

    # Helpful suggestions for common cases
    suggestions = []
    if results["post"].get("error"):
        err = results["post"]["error"]
        if "RemoteDisconnected" in err or "ConnectionResetError" in err or "ConnectionAbortedError" in err:
            suggestions.append("Ollama may be running and immediately closing connections. Check Ollama logs or run it in the same environment as Python.")
        if "ConnectionRefusedError" in err or "Failed to establish a new connection" in err:
            suggestions.append("No service listening on the given host:port from this environment. If Ollama runs in WSL/Docker, either expose the port to Windows or run the script inside WSL.")
    else:
        # If GET returned 405 but POST had 200/4xx that is informative
        if results["get"].get("status_code") == 405 and results["post"].get("status_code"):
            suggestions.append("GET returned 405 (method not allowed) — that's normal for the chat endpoint. Use POST to interact.")
    results["suggestions"] = suggestions
    return results


def _text_from_html_file(path: str) -> str:
    """Very small helper to extract visible text from an HTML file for local testing."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            raw = fh.read()
    except Exception:
        raise
    # Strip script/style and tags — naive but good enough for a quick test
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    # collapse whitespace
    text = re.sub(r"\s+", " ", raw).strip()
    return text


def analyze_filing_from_file(path: str, mock: bool = False, mock_response: Optional[dict] = None) -> Dict:
    """Convenience helper to test analysis locally using a saved raw file.

    - If `mock` is True, returns `mock_response` (or a simple generated result) without calling Ollama.
    - If `mock` is False, extracts text and calls `analyze_filing`.
    """
    logging.debug("analyze_filing_from_file path=%s mock=%s", path, mock)
    text = _text_from_html_file(path)
    if mock:
        if mock_response is not None:
            return mock_response
        # produce a deterministic simple mock response for quick testing
        return {
            "summary_bullets": [text[:200] + "..."],
            "event_type": "mock",
            "impact_level": "unknown",
            "impact_reasoning": "mocked for local testing",
        }
    return analyze_filing(text)


if __name__ == "__main__":
    # Small CLI so a developer can run quick checks without running the whole monitor
    import argparse

    parser = argparse.ArgumentParser(description="Test Ollama LLM wrapper and local file analysis")
    parser.add_argument("--check", action="store_true", help="Run Ollama health check")
    parser.add_argument("--file", type=str, help="Path to saved raw HTML to analyze")
    parser.add_argument("--mock", action="store_true", help="Do not call Ollama; return a mock response")
    args = parser.parse_args()

    if args.check:
        print(json.dumps(check_ollama(), indent=2))
    elif args.file:
        try:
            res = analyze_filing_from_file(args.file, mock=args.mock)
            print(json.dumps(res, indent=2))
        except Exception as e:
            print("Error during analyze_filing_from_file:", e)
            print(traceback.format_exc())
    else:
        parser.print_help()
