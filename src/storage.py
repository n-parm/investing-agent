import sqlite3
from datetime import datetime
from typing import Optional
from pathlib import Path
import json
from .config import DB_PATH

class Storage:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._ensure_tables()

    def _ensure_tables(self):
        c = self.conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_filings (
                accession_number TEXT PRIMARY KEY,
                cik TEXT,
                form_type TEXT,
                filing_date TEXT,
                processed_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts_sent (
                accession_number TEXT PRIMARY KEY,
                sent_at TEXT,
                impact_level TEXT,
                meta JSON
            )
            """
        )
        self.conn.commit()

    def is_processed(self, accession_number: str) -> bool:
        c = self.conn.cursor()
        c.execute(
            "SELECT 1 FROM processed_filings WHERE accession_number = ? LIMIT 1",
            (accession_number,)
        )
        return c.fetchone() is not None

    def mark_processed(self, accession_number: str, cik: str, form_type: str, filing_date: str):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO processed_filings (accession_number, cik, form_type, filing_date, processed_at) VALUES (?,?,?,?,?)",
            (accession_number, cik, form_type, filing_date, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def has_alert(self, accession_number: str) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT 1 FROM alerts_sent WHERE accession_number = ? LIMIT 1", (accession_number,))
        return c.fetchone() is not None

    def mark_alert_sent(self, accession_number: str, impact_level: str, meta: dict | None = None):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO alerts_sent (accession_number, sent_at, impact_level, meta) VALUES (?,?,?,?)",
            (accession_number, datetime.utcnow().isoformat(), impact_level, json.dumps(meta or {})),
        )
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

storage = Storage()
