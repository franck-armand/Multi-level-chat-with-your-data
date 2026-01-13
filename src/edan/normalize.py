from __future__ import annotations

import re
from typing import Optional

_WS = re.compile(r"\s+")
_HYPHEN_SPACES = re.compile(r"\s*-\s*")


def clean_text(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = _WS.sub(" ", s).strip()
    s = _HYPHEN_SPACES.sub("-", s)
    return s


def parse_int(s: str) -> Optional[int]:
    if s is None:
        return None
    s = clean_text(str(s))
    if not s:
        return None
    s2 = s.replace(" ", "").replace(",", "")
    if not re.fullmatch(r"\d+", s2):
        return None
    return int(s2)


def parse_percent(s: str) -> Optional[float]:
    if s is None:
        return None
    s = clean_text(str(s))
    if not s:
        return None
    s = s.replace("%", "").replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_score_or_int(s: str) -> Optional[int]:
    return parse_int(s)
