"""Orchestrator for fetching, filtering, analyzing, alerting, and persisting state."""
import traceback
from time import sleep
from .config import TRACKED_COMPANIES
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

        if not prefilter(text):
            print(f"Prefilter rejected {acc} (too short or boilerplate)")
            storage.mark_processed(acc, cik, f.get("form_type"), f.get("filing_date"))
            continue

        # Optional dedupe via hash could be persisted in future. For now compute hash for logging.
        thash = text_hash(text)
        print(f"Text hash: {thash[:10]}...")

        try:
            analysis = analyze_filing(text)
        except Exception as e:
            print(f"LLM analysis failed for {acc}: {e}")
            # Per MVP rule: discard on JSON parse failure, mark processed so we don't retry.
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
