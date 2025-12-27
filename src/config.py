from pathlib import Path
import os

# Single source of truth for tracked companies and runtime configuration
TRACKED_COMPANIES = {
    "GEHC": {"cik": "0001932393"}
}

ALERT_MIN_IMPACT = "Medium"

# Ollama model identifier (MVP)
OLLAMA_MODEL = "llama3:latest"

# Max characters of filing text to feed the LLM
MAX_FILING_CHARS = 15_000

# Full Ollama HTTP API URL (can be overridden with env var OLLAMA_URL)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")

# SQLite DB path (relative to project)
DB_PATH = str(Path(__file__).parent / "db.sqlite")

# SEC request headers (User-Agent required by SEC)
SEC_HEADERS = {
    "User-Agent": "SmartMarketMonitor/0.1 (n-parm@example.com)",
    "Accept": "application/json, text/html",
}

# SMTP placeholders for sending email alerts (fill before running)
SMTP = {
    "host": "smtp.example.com",
    "port": 587,
    "username": "you@example.com",
    "password": "CHANGE_ME",
    "from_addr": "alerts@example.com",
    "to_addrs": ["you@example.com"],
}
