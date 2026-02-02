from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from .normalize import normalize_for_match
from .vocab import Vocab


STOPWORDS = {
    "seat", "seats", "siege", "sieges",
    "won", "win", "winners", "winner",
    "how", "many", "by", "party", "parties",
    "in", "region", "show", "top",
    "histogram", "bar", "pie", "chart", "plot", "graph",
    "of", "the", "a", "an", "to", "for", "from",
    "participation", "turnout", "rate",
    "candidate", "candidates",
}

# Key length rules for party matching:
# - We DO allow 3-letter party tokens like "rda", "fpi", "ppaci" etc.
# - We DO NOT allow 1-2 letter tokens like "ci" (too ambiguous).
MIN_PARTY_TOKEN_LEN = 3
MIN_PARTY_FULL_KEY_LEN = 3


@dataclass
class Resolved:
    party: Optional[str] = None
    region: Optional[str] = None
    circonscription: Optional[str] = None
    candidate: Optional[str] = None
    circonscription_code: Optional[str] = None
    notes: List[str] = field(default_factory=list)


def _normalize_party_key(s: str) -> str:
    """
    Compact party key: lower, strip accents, remove punctuation/spaces/hyphens.
    """
    s = normalize_for_match(s)
    return re.sub(r"[^a-z0-9]", "", s)


def _ngrams(tokens: List[str], min_n: int = 1, max_n: int = 4) -> List[str]:
    spans: List[str] = []
    for n in range(min_n, max_n + 1):
        for i in range(len(tokens) - n + 1):
            spans.append(" ".join(tokens[i:i+n]))
    spans.sort(key=lambda x: (-len(x.split()), x))  # prefer longer spans
    return spans


def _best_fuzzy(query: str, choices: List[str], cutoff: float) -> Optional[str]:
    """
    Fuzzy match query against choices (already normalized strings).
    Uses rapidfuzz partial_ratio if available; fallback to difflib.
    """
    if not query or not choices:
        return None

    try:
        from rapidfuzz import process, fuzz  # type: ignore
        match = process.extractOne(query, choices, scorer=fuzz.partial_ratio)
        if match and (match[1] / 100.0) >= cutoff:
            return match[0]
        return None
    except Exception:
        matches = difflib.get_close_matches(query, choices, n=1, cutoff=cutoff)
        return matches[0] if matches else None


def _best_span_match(spans: List[str], choices_norm: List[str], cutoff: float) -> Optional[str]:
    for sp in spans:
        hit = _best_fuzzy(sp, choices_norm, cutoff=cutoff)
        if hit:
            return hit
    return None


def _build_party_alias_map(parties: List[str]) -> Dict[str, str]:
    """
    Build alias keys for parties automatically from the dataset.

    RULES:
    - Always index the FULL compact key (e.g. "pdcirdaeds", "reelci", "pdcifpiadci").
    - For NON-COALITION parties (single part), also index token keys (e.g. "fpi") and acronyms.
    - For COALITIONS (>=2 parts), DO NOT index single-token aliases (prevents "fpi" matching "PDCI-FPI-ADCI").
    """
    mapping: Dict[str, str] = {}

    for p in parties:
        canon = p

        # Full key always
        full_key = _normalize_party_key(p)
        if len(full_key) >= MIN_PARTY_FULL_KEY_LEN:
            mapping[full_key] = canon

        # Split on whitespace and hyphen
        norm = normalize_for_match(p)              # e.g. "pdci-rda-eds" or "reel ci"
        parts = re.split(r"[\s\-]+", norm)
        parts = [x for x in parts if x]

        is_coalition = len(parts) >= 2

        # Only index token aliases for non-coalitions
        if not is_coalition:
            for w in parts:
                k = _normalize_party_key(w)
                if len(k) >= MIN_PARTY_TOKEN_LEN:
                    mapping[k] = canon

            # Acronym for single-part names (rare, but harmless)
            acronym = _normalize_party_key("".join(w[0] for w in parts if w and w[0].isalnum()))
            if len(acronym) >= MIN_PARTY_TOKEN_LEN:
                mapping[acronym] = canon

        # For coalitions, we intentionally do NOT index short tokens like "fpi", "pdci", etc.
        # They are too ambiguous and should be handled by Level 3 disambiguation.

    return mapping


def _extract_acronyms(tokens: List[str]) -> List[str]:
    """
    Join consecutive single-letter tokens into acronyms:
      ["p","d","c","i"] -> "pdci"
      ["r","h","d","p"] -> "rhdp"
    Return list of acronym strings (normalized keys).
    """
    acronyms: List[str] = []
    buf: List[str] = []

    def flush():
        nonlocal buf
        if len(buf) >= 3:  # only meaningful acronyms
            acronyms.append("".join(buf))
        buf = []

    for t in tokens:
        if len(t) == 1 and t.isalnum():
            buf.append(t)
        else:
            flush()
    flush()

    return [_normalize_party_key(a) for a in acronyms if len(_normalize_party_key(a)) >= MIN_PARTY_TOKEN_LEN]


def resolve_entities(user_text: str, vocab: Vocab) -> Resolved:
    notes: List[str] = []
    q_norm = normalize_for_match(user_text)

    # Code detection
    code = None
    m = re.search(r"\bcode\s+(\d{1,3})\b", q_norm)
    if m:
        code = m.group(1).zfill(3)
        notes.append(f"Detected circonscription_code={code}")

    # Tokenize and remove stopwords
    raw_tokens = q_norm.split()
    tokens = [t for t in raw_tokens if t not in STOPWORDS]
    spans = _ngrams(tokens, 1, 4)

    # PARTY
    party = None
    party_alias = _build_party_alias_map(vocab.parties)

    # 1) Prefer acronym matching first (P.D.C.I, R.H.D.P, etc.)
    acronyms = _extract_acronyms(tokens)
    for a in acronyms:
        if a in party_alias:
            party = party_alias[a]
            notes.append(f"Resolved party from acronym '{a}' -> {party}")
            break

    # 2) Then try span-based matching (but only keys >= MIN_PARTY_TOKEN_LEN)
    if party is None:
        for sp in spans:
            k = _normalize_party_key(sp)
            if len(k) < MIN_PARTY_TOKEN_LEN:
                continue
            if k in party_alias:
                party = party_alias[k]
                notes.append(f"Resolved party from span '{sp}' -> {party}")
                break

    # REGION (span fuzzy)
    region = None
    region_norms = [normalize_for_match(r) for r in vocab.regions]
    region_hit = _best_span_match(spans, region_norms, cutoff=0.85)
    if region_hit:
        region = next((r for r in vocab.regions if normalize_for_match(r) == region_hit), None)
        if region:
            notes.append(f"Resolved region -> {region}")

    # CIRCONSCRIPTION (span fuzzy)
    circo = None
    circo_norms = [normalize_for_match(c) for c in vocab.circo_names]
    circo_hit = _best_span_match(spans, circo_norms, cutoff=0.85)
    if circo_hit:
        circo = next((c for c in vocab.circo_names if normalize_for_match(c) == circo_hit), None)
        if circo:
            notes.append(f"Resolved circonscription -> {circo}")

    # CANDIDATE (span fuzzy, stricter)
    candidate = None
    cand_norms = [normalize_for_match(c) for c in vocab.candidates]
    cand_hit = _best_span_match(spans, cand_norms, cutoff=0.90)
    if cand_hit:
        candidate = next((c for c in vocab.candidates if normalize_for_match(c) == cand_hit), None)
        if candidate:
            notes.append(f"Resolved candidate -> {candidate}")

    return Resolved(
        party=party,
        region=region,
        circonscription=circo,
        candidate=candidate,
        circonscription_code=code,
        notes=notes,
    )