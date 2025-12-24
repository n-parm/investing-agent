from typing import Dict, Tuple
from .config import ALERT_MIN_IMPACT

IMPACT_RANK = {"None": 0, "Low": 1, "Medium": 2, "High": 3}

def should_alert(analysis: Dict) -> bool:
    level = analysis.get("impact_level", "None")
    return IMPACT_RANK.get(level, 0) >= IMPACT_RANK.get(ALERT_MIN_IMPACT, 2)

def format_alert(symbol: str, filing: Dict, analysis: Dict) -> Tuple[str, str]:
    subject = f"[Market Alert] {symbol} – {analysis.get('impact_level', 'Unknown')} Impact {filing.get('form_type')}"
    body_lines = []
    body_lines.append(f"Event: {analysis.get('event_type', 'Other')}")
    body_lines.append(f"Impact: {analysis.get('impact_level', 'Unknown')}")
    body_lines.append("")
    body_lines.append("Summary:")
    for b in analysis.get("summary_bullets", [])[:5]:
        body_lines.append(f"- {b}")
    body_lines.append("")
    body_lines.append("Reasoning:")
    body_lines.append(analysis.get("impact_reasoning", ""))
    body = "\n".join(body_lines)
    return subject, body
