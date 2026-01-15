from __future__ import annotations
import re
import unicodedata


_WS = re.compile(r"\s+")


def strip_accents(s: str) -> str:
    # Côte -> Cote
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_for_match(s: str) -> str:
    s = s.lower().strip()
    s = strip_accents(s)
    s = re.sub(r"[^a-z0-9\s\-']", " ", s)  # keep hyphen/apostrophe
    s = _WS.sub(" ", s).strip()
    return s
