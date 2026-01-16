from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from edan.entities.vocab import load_vocab
from edan.entities.resolve import resolve_entities
from edan.entities.normalize import normalize_for_match
from edan.rag.retriever import retrieve
from edan.level3.state import Choice

def memory_key_from_query(user_query: str) -> Optional[str]:
    mention = extract_location_mention(user_query)
    if not mention:
        return None
    return normalize_for_match(mention)


def _sql_str(s: str) -> str:
    return s.replace("'", "''")


def _is_turnout_query(q: str) -> bool:
    ql = q.lower()
    return any(x in ql for x in ["turnout", "participation", "votants", "inscrits", "exprimes", "blancs", "nuls"])


def _is_winner_query(q: str) -> bool:
    ql = q.lower()
    return any(x in ql for x in ["who won", "winner", "winners", "elu", "gagn"])


def extract_location_mention(q: str) -> Optional[str]:
    # naive heuristic: "in X" / "dans X"
    qn = normalize_for_match(q)
    m = re.search(r"\b(in|dans|a)\s+(.+)$", qn)
    if not m:
        return None
    return m.group(2).strip()


def _extract_top_n(q: str, default: int = 5) -> int:
    m = re.search(r"\btop\s+(\d+)\b", q.lower())
    return int(m.group(1)) if m else default


def _contains_metric_hint(q: str) -> bool:
    ql = q.lower()
    # If user already specified what “top” means, we don't clarify here.
    return any(x in ql for x in [
        "candidate", "candidates", "score",
        "turnout", "participation",
        "winner", "winners",
        "votes", "seats", "siege", "sieges"
    ])


def propose_choices(user_query: str, db_path: Path, memory: Dict[str, Any]) -> Tuple[bool, str, List[Choice]]:
    """
    Returns (needs_clarification, question, choices)
    """
    vocab = load_vocab(db_path)
    resolved = resolve_entities(user_query, vocab)
    q_norm = normalize_for_match(user_query)
    mention = extract_location_mention(user_query)

    # If we already have a remembered mapping for a mention, no clarification needed
    k = memory_key_from_query(user_query)
    if k and k in memory:
        return False, "", []

    choices: List[Choice] = []

    # ---- Metric ambiguity: "Top N in <X>" (Level 3)
    if "top" in user_query.lower() and not _contains_metric_hint(user_query):
        mention = extract_location_mention(user_query)
        if mention:
            n = _extract_top_n(user_query, default=5)
            choices = [
                Choice(
                    key="top:candidates",
                    label=f"Top {n} candidates by score",
                    payload={"mode": "top_candidates", "place": mention, "n": n},
                ),
                Choice(
                    key="top:turnout",
                    label=f"Top {n} circonscriptions by turnout rate",
                    payload={"mode": "top_turnout", "place": mention, "n": n},
                ),
                Choice(
                    key="top:winners_party",
                    label=f"Winners by party (counts) for {mention}",
                    payload={"mode": "winners_by_party", "place": mention, "n": n},
                ),
            ]
            return True, "Top N is ambiguous. What do you mean by “Top” here?", choices

    
    # ---- Scope ambiguity: turnout in <place> (region summary vs per-circo list)
    if _is_turnout_query(user_query):
        # If a region is resolved but no circonscription code/name, ask scope question
        if resolved.region and not resolved.circonscription_code and not resolved.circonscription:
            region = resolved.region
            choices.append(
                Choice(
                    key=f"turnout:region:{region}",
                    label=f"Turnout summary for region: {region}",
                    payload={"mode": "turnout_region_summary", "region": region},
                )
            )
            choices.append(
                Choice(
                    key=f"turnout:list:{region}",
                    label=f"List turnout for all circonscriptions in region: {region}",
                    payload={"mode": "turnout_region_list", "region": region},
                )
            )
            return True, "Your request is ambiguous. Do you want a regional summary or turnout per circonscription?", choices
        
        # if not resolved, use RAG hits to infer likely region(s)
        if mention:
            hits = retrieve(db_path, mention, k=10)
            regions = []
            seen = set()
            for h in hits:
                if h.region and h.region not in seen:
                    seen.add(h.region)
                    regions.append(h.region)

            # If we got at least one region candidate, ask scope question
            if regions:
                # If multiple regions, offer them; most often 1 (Abidjan district)
                for reg in regions[:3]:
                    choices.append(
                        Choice(
                            key=f"turnout:region:{reg}",
                            label=f"Turnout summary for region: {reg}",
                            payload={"mode": "turnout_region_summary", "region": reg},
                        )
                    )
                    choices.append(
                        Choice(
                            key=f"turnout:list:{reg}",
                            label=f"List turnout for all circonscriptions in region: {reg}",
                            payload={"mode": "turnout_region_list", "region": reg},
                        )
                    )
                return True, "Your request is ambiguous. Do you want a regional summary or turnout per circonscription?", choices

    # ---- Winner ambiguity: "Who won in <X>?" where X could map to multiple circonscription codes
    if _is_winner_query(user_query) and mention:
        hits = retrieve(db_path, mention, k=8)
        codes = []
        seen = set()
        for h in hits:
            if h.circonscription_code and h.circonscription_code not in seen:
                seen.add(h.circonscription_code)
                codes.append((h.circonscription_code, h.region))
        if len(codes) >= 2:
            for code, region in codes[:6]:
                choices.append(
                    Choice(
                        key=f"winner:code:{code}",
                        label=f"Winner for circonscription code {code} (region {region})",
                        payload={"mode": "winner_code", "circonscription_code": code},
                    )
                )
            return True, "I found multiple possible matches. Which circonscription did you mean?", choices

    # ---- Party ambiguity (Level 3): if seats query mentions acronym (PDCI etc.), ask which label
    if "seat" in user_query.lower() or "seats" in user_query.lower() or "siege" in user_query.lower():
        # if party resolved is empty but mention looks like acronym, offer party matches, this is optional; we keep it simple:
        pass

    return False, "", []


def parse_selection(selection: str, choices: List[Choice]) -> Optional[Choice]:
    """
    Accept:
      - '1', '2'
      - 'option 1'
      - exact substring match on label
    """
    s = selection.strip().lower()

    m = re.search(r"(\d+)", s)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(choices):
            return choices[idx]

    # label substring
    for c in choices:
        if c.label.lower() in s or s in c.label.lower():
            return c

    return None


def apply_choice_and_update_memory(user_query: str, choice: Choice, memory: Dict[str, Any]) -> Dict[str, Any]:
    k = memory_key_from_query(user_query)
    if k:
        memory[k] = choice.payload
    return memory


def run_sql_for_choice(db_path: Path, payload: Dict[str, Any]) -> Tuple[str, str]:
    """
    Returns (sql, narrative). For place-based queries, we use RAG retrieval to infer
    the most likely circonscription_code or region.
    """
    mode = payload.get("mode")
    place = payload.get("place", "")
    n = int(payload.get("n", 5))

    # Helper: infer best circonscription_code + region from RAG
    def infer_from_place(p: str) -> Tuple[Optional[str], Optional[str]]:
        hits = retrieve(db_path, p, k=10)
        if not hits:
            return None, None

        # choose best match (top hit)
        best_code = hits[0].circonscription_code
        best_region = hits[0].region

        # also gather most common region among hits (helps "Abidjan")
        region_counts: Dict[str, int] = {}
        for h in hits:
            if h.region:
                region_counts[h.region] = region_counts.get(h.region, 0) + 1
        if region_counts:
            best_region = sorted(region_counts.items(), key=lambda x: x[1], reverse=True)[0][0]

        return best_code, best_region

    def s(s: str) -> str:
        return _sql_str(s)

    if mode == "turnout_region_summary":
        region = s(payload["region"])
        sql = f"""
        SELECT region,
               AVG(taux_participation) AS avg_participation,
               SUM(votants) AS total_votants,
               SUM(inscrits) AS total_inscrits
        FROM vw_turnout
        WHERE region = '{region}'
        GROUP BY region;
        """
        return sql, f"Turnout summary for region **{payload['region']}**:"

    if mode == "turnout_region_list":
        region = s(payload["region"])
        sql = f"""
        SELECT region, circonscription_code, circonscription_name, taux_participation, votants, inscrits
        FROM vw_turnout
        WHERE region = '{region}'
        ORDER BY circonscription_code;
        """
        return sql, f"Turnout per circonscription in region **{payload['region']}**:"

    if mode == "winner_code":
        code = s(payload["circonscription_code"])
        sql = f"""
        SELECT region, circonscription_code, circonscription_name, party, candidate, score
        FROM vw_winners
        WHERE circonscription_code = '{code}';
        """
        return sql, f"Winner for circonscription code **{payload['circonscription_code']}**:"

    # ---- Level 3 Top-N modes ----
    if mode == "top_candidates":
        code, _region = infer_from_place(place)
        if not code:
            return "", f"Not found in the provided PDF dataset (could not locate **{place}**)."

        code_sql = s(code)
        sql = f"""
        SELECT candidate, party, score, score_percent, elected
        FROM vw_results_clean
        WHERE circonscription_code = '{code_sql}'
        ORDER BY score DESC
        LIMIT {n};
        """
        return sql, f"Top **{n}** candidates by score for **{place}** (matched code **{code}**):"

    if mode == "top_turnout":
        _code, region = infer_from_place(place)
        if not region:
            return "", f"Not found in the provided PDF dataset (could not locate **{place}**)."

        region_sql = s(region)
        sql = f"""
        SELECT region, circonscription_code, circonscription_name, taux_participation, votants, inscrits
        FROM vw_turnout
        WHERE region = '{region_sql}'
        ORDER BY taux_participation DESC
        LIMIT {n};
        """
        return sql, f"Top **{n}** circonscriptions by turnout rate in **{region}** (inferred from “{place}”):"

    if mode == "winners_by_party":
        _code, region = infer_from_place(place)
        if not region:
            return "", f"Not found in the provided PDF dataset (could not locate **{place}**)."

        region_sql = s(region)
        sql = f"""
        SELECT party, COUNT(*) AS winners
        FROM vw_winners
        WHERE region = '{region_sql}'
        GROUP BY party
        ORDER BY winners DESC;
        """
        return sql, f"Winners by party in **{region}** (inferred from “{place}”):"

    return "", "Unsupported selection."

