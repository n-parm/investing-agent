"""Orchestrator for fetching, filtering, analyzing, alerting, and persisting state."""
import traceback
from time import sleep
from pathlib import Path
import requests

from .config import TRACKED_COMPANIES, SEC_HEADERS
from .storage import storage
from .edgar import fetch_filings, extract_text
from .filters import prefilter, text_hash
from .llm import analyze_filing
from .alerts import should_alert, format_alert
from .emailer import send_email

def process_company(symbol: str, company: dict):
    cik = company.get("cik")
    print(f"Checking filings for {symbol} (CIK={cik})")
    filings = fetch_filings(cik)
    for f in filings:
        acc = f["accession_number"]
        if storage.is_processed(acc):
            # Stop once we hit already-seen filing (list is newest->oldest)
            print(f"Already processed {acc}; stopping further older filings for {symbol}.")
            break

        try:
            print(f"Fetching primary doc for {symbol} {acc} -> {f['primary_doc_url']}")
            text = extract_text(f["primary_doc_url"])
        except Exception as e:
            print(f"Failed to fetch/extract {acc}: {e}")
            continue

        # Per-form minimum length thresholds (characters)
        FORM_MIN_CHARS = {
            "4": 300,
            "3": 300,
            "5": 300,
            "8-K": 800,
            "10-Q": 2000,
            "10-K": 3000,
            "13F-HR": 1000,
            "S-1": 2000,
            "SC 13G": 800,
            "SC 13D": 800,
        }

        form = (f.get("form_type") or "").upper().strip()
        min_chars = FORM_MIN_CHARS.get(form, 1500)

        # Log text length for tuning thresholds
        text_len = len(text) if text else 0
        print(f"Text length for {acc}: {text_len} characters (min required: {min_chars})")

        # If the extracted text is unexpectedly short, save the raw response
        # so you can inspect it locally (helps diagnose SEC blocks or parser
        # issues). Files are written to src/debug_raw/{accession}.html
        # if text_len < max(500, min_chars):
        try:
            debug_dir = Path(__file__).parent / "debug_raw"
            debug_dir.mkdir(exist_ok=True)
            raw_path = debug_dir / f"{acc}.html"
            r = requests.get(f["primary_doc_url"], headers=SEC_HEADERS, timeout=20)
            r.raise_for_status()
            raw_path.write_text(r.text, encoding="utf-8")
            print(f"Saved raw response for {acc} to {raw_path}")
        except Exception as e:
            print(f"Failed to save raw response for {acc}: {e}")

        if not prefilter(text, min_chars=min_chars):
            print(f"Prefilter rejected {acc} (too short or boilerplate) - length {text_len} < {min_chars}")
            storage.mark_processed(acc, cik, f.get("form_type"), f.get("filing_date"))
            continue

        # Optional dedupe via hash could be persisted in future. For now compute hash for logging.
        thash = text_hash(text)
        # print(f"Text hash: {thash[:10]}...")

        try:
            analysis = analyze_filing(text)
        except Exception as e:
            print(f"LLM analysis failed for {acc}: {e}")
            # Discard on JSON parse failure for now, mark processed so we don't retry.
            storage.mark_processed(acc, cik, f.get("form_type"), f.get("filing_date"))
            continue

        if should_alert(analysis) and not storage.has_alert(acc):
            subject, body = format_alert(symbol, f, analysis)
            try:
                send_email(subject, body)
                storage.mark_alert_sent(acc, analysis.get("impact_level", "None"), {"symbol": symbol})
                print(f"Alert sent for {acc}")
            except Exception as e:
                print(f"Failed to send alert for {acc}: {e}")
        else:
            print(f"No alert for {acc} (impact {analysis.get('impact_level')})")

        # Mark processed regardless so we don't reprocess repeatedly
        storage.mark_processed(acc, cik, f.get("form_type"), f.get("filing_date"))

def main(poll_once: bool = True):
    try:
        for symbol, company in TRACKED_COMPANIES.items():
            try:
                process_company(symbol, company)
            except Exception:
                print(f"Error processing {symbol}:\n" + traceback.format_exc())
        if not poll_once:
            # Sleep and repeat (cron alternative)
            while True:
                sleep(1800)
                for symbol, company in TRACKED_COMPANIES.items():
                    process_company(symbol, company)
    finally:
        try:
            storage.close()
        except Exception:
            pass

if __name__ == "__main__":
    # Run once by default. Use `python -m src.run_monitor` from project root.
    main(poll_once=True)
