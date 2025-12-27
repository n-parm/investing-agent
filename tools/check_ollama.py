"""Run a quick Ollama connectivity diagnostic from this environment.

Usage:
    python tools/check_ollama.py

This imports `check_ollama` from `src.llm` and prints a JSON summary.
"""
import json
import sys
import os

# Ensure the project root is on sys.path so `src` can be imported when running
# this script directly from the repository root.
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from src.llm import check_ollama

if __name__ == "__main__":
    res = check_ollama()
    print(json.dumps(res, indent=2))
    # Exit non-zero when not OK to make CI/automation easy
    sys.exit(0 if res.get("ok") else 2)
