import requests
import warnings
from bs4 import BeautifulSoup, FeatureNotFound
from typing import List
from .config import SEC_HEADERS, MAX_FILING_CHARS

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

def fetch_filings(cik: str) -> List[dict]:
    """
    Returns list of filings (recent) from SEC submissions endpoint.

    Each item:
      {
        "accession_number": str,
        "form_type": str,
        "filing_date": str,
        "primary_doc": str,
        "primary_doc_url": str
      }
    """
    # The SEC submissions endpoint expects the CIK zero-padded to 10 digits
    cik_padded = str(cik).zfill(10)
    url = SEC_SUBMISSIONS_URL.format(cik=cik_padded)
    r = requests.get(url, headers=SEC_HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()

    filings = []
    recent = data.get("filings", {}).get("recent", {})
    accession_list = recent.get("accessionNumber", [])
    form_list = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    for acc, form, fdate, pdoc in zip(accession_list, form_list, filing_dates, primary_docs):
        # Build a best-effort primary doc URL. This matches typical EDGAR archive layout.
        acc_no = acc.replace("-", "")
        try:
            cik_int = str(int(cik))
        except Exception:
            cik_int = cik
        primary_doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no}/{pdoc}"
        filings.append(
            {
                "accession_number": acc,
                "form_type": form,
                "filing_date": fdate,
                "primary_doc": pdoc,
                "primary_doc_url": primary_doc_url,
            }
        )

    # Keep only forms we care about
    wanted = {"8-K", "10-Q", "10-K", "4"}
    filtered = [f for f in filings if f["form_type"] in wanted]

    # Sort by filing_date descending
    filtered.sort(key=lambda x: x.get("filing_date", ""), reverse=True)
    return filtered

def extract_text(url: str) -> str:
    r = requests.get(url, headers=SEC_HEADERS, timeout=20)
    r.raise_for_status()
    try:
        soup = BeautifulSoup(r.text, "xml")
    except FeatureNotFound:
        warnings.warn("xml parser not available; falling back to html.parser")
        soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(separator="\n")
    return text[:MAX_FILING_CHARS]
