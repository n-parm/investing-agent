"""Orchestrator for fetching, filtering, analyzing, alerting, and persisting state."""
import traceback
from time import sleep
from pathlib import Path
import requests
from datetime import datetime
import logging

from .config import TRACKED_COMPANIES, SEC_HEADERS, OLLAMA_URL
from .storage import storage
from .edgar import fetch_filings, extract_text
from .filters import prefilter, text_hash
from .llm import analyze_filing, check_ollama
from .alerts import should_alert, format_alert
from .emailer import send_email

# Setup basic logging with timestamps
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)-8s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def process_company(symbol: str, company: dict):
    cik = company.get("cik")
    logger.info(f"Starting processing for {symbol} (CIK={cik})")
    print(f"\n{'='*70}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing {symbol} (CIK={cik})")
    print(f"{'='*70}")
    filings = fetch_filings(cik)
    logger.debug(f"Fetched {len(filings)} filings for {symbol}")
    print(f"Found {len(filings)} filings")
    for f in filings:
        acc = f["accession_number"]
        if storage.is_processed(acc):
            # Stop once we hit already-seen filing (list is newest->oldest)
            logger.debug(f"Already processed {acc}; stopping further older filings for {symbol}")
            print(f"Already processed {acc}; stopping")
            break

        try:
            logger.debug(f"Fetching primary doc for {symbol} {acc}")
            print(f"  [FETCH] {acc} from {f['primary_doc_url'][:80]}...")
            text = extract_text(f["primary_doc_url"])
            logger.debug(f"Successfully extracted text for {acc}, length={len(text) if text else 0}")
        except Exception as e:
            logger.error(f"Failed to fetch/extract {acc}: {e}")
            print(f"  [ERROR] Failed to fetch {acc}: {e}")
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
        logger.info(f"Text length for {acc}: {text_len} chars (form: {form}, min required: {min_chars})")
        print(f"  [TEXT] {text_len} chars (form={form}, min={min_chars})")

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
            logger.info(f"Prefilter rejected {acc} (length {text_len} < {min_chars})")
            print(f"  [SKIP] Prefilter rejected: text too short ({text_len} < {min_chars})")
            storage.mark_processed(acc, cik, f.get("form_type"), f.get("filing_date"))
            continue

        # Optional dedupe via hash could be persisted in future. For now compute hash for logging.
        thash = text_hash(text)
        # print(f"Text hash: {thash[:10]}...")

        try:
            logger.info(f"Starting LLM analysis for {acc} (chars={text_len})...")
            print(f"  [LLM] Analyzing with Ollama at {OLLAMA_URL}...")
            analysis = analyze_filing(text)
            logger.info(f"LLM analysis completed for {acc}: impact_level={analysis.get('impact_level')}")
            print(f"  [LLM] Analysis complete: impact={analysis.get('impact_level')}")
        except Exception as e:
            logger.error(f"LLM analysis FAILED for {acc}: {type(e).__name__}: {e}")
            print(f"  [ERROR] LLM analysis failed: {e}")
            # Discard on JSON parse failure for now, mark processed so we don't retry.
            storage.mark_processed(acc, cik, f.get("form_type"), f.get("filing_date"))
            continue

        if should_alert(analysis) and not storage.has_alert(acc):
            logger.info(f"Alert triggered for {acc} (impact: {analysis.get('impact_level')})")
            subject, body = format_alert(symbol, f, analysis)
            try:
                print(f"  [ALERT] Sending email for {acc}...")
                send_email(subject, body)
                storage.mark_alert_sent(acc, analysis.get("impact_level", "None"), {"symbol": symbol})
                logger.info(f"Alert email sent for {acc}")
                print(f"  [ALERT] Email sent successfully")
            except Exception as e:
                logger.error(f"Failed to send alert for {acc}: {e}")
                print(f"  [ERROR] Failed to send alert email: {e}")
        else:
            logger.debug(f"No alert for {acc} (impact {analysis.get('impact_level')})")
            print(f"  [SKIP] No alert (impact={analysis.get('impact_level')})")

        # Mark processed regardless so we don't reprocess repeatedly
        storage.mark_processed(acc, cik, f.get("form_type"), f.get("filing_date"))
        logger.info(f"Completed processing for {acc}")

def main(poll_once: bool = True):
    logger.info("="*70)
    logger.info(f"Monitor started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Ollama URL configured: {OLLAMA_URL}")
    logger.info(f"Poll once mode: {poll_once}")
    
    # Run upfront Ollama connectivity check
    logger.info("Running Ollama connectivity check...")
    print("\n" + "="*70)
    print("OLLAMA CONNECTIVITY CHECK")
    print("="*70)
    ollama_status = check_ollama()
    logger.info(f"Ollama check results: {ollama_status}")
    print(f"URL: {ollama_status.get('url')}")
    print(f"GET result: {ollama_status.get('get')}")
    print(f"POST result: {ollama_status.get('post')}")
    print(f"Status OK: {ollama_status.get('ok')}")
    if ollama_status.get('suggestions'):
        print("\nSuggestions:")
        for suggestion in ollama_status['suggestions']:
            print(f"  - {suggestion}")
    
    if not ollama_status.get('ok'):
        logger.warning("Ollama connectivity check FAILED. Proceeding anyway, but LLM analysis will likely fail.")
        print("\nWARNING: Ollama connectivity check failed! Analysis will likely timeout.")
    else:
        logger.info("Ollama connectivity check PASSED")
        print("\nOllama connectivity check passed")
    
    print("="*70 + "\n")
    
    try:
        for symbol, company in TRACKED_COMPANIES.items():
            try:
                process_company(symbol, company)
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)
                print(f"\n[ERROR] Exception processing {symbol}:")
                print(traceback.format_exc())
        if not poll_once:
            # Sleep and repeat (cron alternative)
            while True:
                logger.info("Poll cycle complete, sleeping for 30 minutes...")
                sleep(1800)
                for symbol, company in TRACKED_COMPANIES.items():
                    process_company(symbol, company)
    finally:
        try:
            logger.info("Closing storage connection...")
            storage.close()
            logger.info("Monitor completed")
        except Exception as e:
            logger.error(f"Error closing storage: {e}")

if __name__ == "__main__":
    # Run once by default. Use `python -m src.run_monitor` from project root.
    try:
        main(poll_once=True)
    except KeyboardInterrupt:
        logger.info("Monitor interrupted by user")
        print("\n[INTERRUPTED] Monitor stopped by user")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        print(f"\n[CRITICAL ERROR]: {e}")
        print(traceback.format_exc())
        raise
