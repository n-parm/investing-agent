import hashlib

BOILERPLATE_PHRASES = [
    "forward-looking statements",
]

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def prefilter(text: str, min_chars: int = 1500) -> bool:
    """Return True if text should be kept (passes filters).

    Rules:
    - Minimum length
    - No boilerplate phrases
    """
    if not text:
        return False
    if len(text) < min_chars:
        return False
    lower = text.lower()
    for p in BOILERPLATE_PHRASES:
        if p in lower:
            return False
    return True
