from __future__ import annotations

import re
from edan.entities.normalize import normalize_for_match
from pathlib import Path
from typing import Any, Dict, List

from edan.entities.vocab import load_vocab
from edan.entities.resolve import resolve_entities
from edan.level2.state import L2State, Citation
from edan.agent.agent import plan_question, looks_malicious  # reuse Level 1 planner
from edan.sql.exec import run_query
from edan.rag.retriever import retrieve
from edan.level2.answer import (
    answer_from_sql_local,
    answer_from_rag_local,
    format_citations,
    enhance_with_openai_if_enabled,
)


def node_resolve(state: L2State) -> L2State:
    vocab = load_vocab(Path(state.db_path))
    state.resolved = resolve_entities(state.user_query, vocab)
    return state


def node_route(state: L2State) -> L2State:
    q = state.user_query
    q_low = q.lower()
    q_norm = normalize_for_match(q)

    # 0) Safety first
    if looks_malicious(q):
        state.route = "blocked"
        state.answer = (
            "I can't help with destructive or exfiltration requests. "
            "Ask an analytics question about the dataset instead."
        )
        return state
    
    # If user just asks a party name, treat it as a valid query (hybrid)
    if state.resolved and state.resolved.party and len(normalize_for_match(q).split()) <= 3:
        party = state.resolved.party.replace("'", "''")
        state.route = "sql"
        state.sql = f"""
        SELECT
            '{party}' AS party,
            (SELECT COUNT(*) FROM vw_winners WHERE party = '{party}') AS winners,
            (SELECT SUM(score) FROM vw_results_clean WHERE party = '{party}') AS total_votes
        ;
        """
        return state
    
    # 1) If Level 1 planner can handle it, prefer that SQL (charts/rankings already implemented there)
    plan = plan_question(q)
    if plan is not None:
        state.route = "sql"
        state.sql = plan.sql
        return state

    # Helper: detect analytics intent (Level 2 requirement)
    analytics_keywords = [
        "how many", "count", "number of", "top", "rank", "seats", "siege", "turnout",
        "participation", "average", "avg", "sum", "total", "by region", "by party",
    ]
    is_analytics = any(k in q_low for k in analytics_keywords)

    # Helper: extract acronym from single-letter tokens in user query: "p d c i" -> "pdci"
    def extract_acronym(norm_text: str) -> str | None:
        toks = norm_text.split()
        buf = []
        acronyms = []
        for t in toks:
            if len(t) == 1 and t.isalnum():
                buf.append(t)
            else:
                if len(buf) >= 3:
                    acronyms.append("".join(buf))
                buf = []
        if len(buf) >= 3:
            acronyms.append("".join(buf))
        # take the longest acronym
        if not acronyms:
            return None
        acronyms.sort(key=len, reverse=True)
        return acronyms[0]

    # Helper: safe SQL string literal
    def sql_str(s: str) -> str:
        return s.replace("'", "''")

    # 2.0) GLOBAL TOTALS (use vw_turnout to avoid duplicate candidate rows)
    if "total" in q_low:
        metric_map = {
            "inscrits": "inscrits",
            "registered": "inscrits",
            "register": "inscrits",
            "votants": "votants",
            "voters": "votants",
            "votes": "votants", 
            "exprimes": "suf_exprimes",
            "expressed": "suf_exprimes",
            "nuls": "bull_nuls",
            "null": "bull_nuls",
            "blancs": "bull_blancs_nbr",
            "blank": "bull_blancs_nbr",
        }

        # decide which metric user likely wants
        chosen = None
        for k, col in metric_map.items():
            if k in q_low:
                chosen = col
                break

        # special case: "total votes by candidates" -> sum(score)
        if "candidate" in q_low or "candidates" in q_low:
            state.route = "sql"
            state.sql = "SELECT SUM(score) AS total_candidate_votes FROM vw_results_clean;"
            return state

        if chosen:
            state.route = "sql"
            state.sql = f"SELECT SUM({chosen}) AS total_{chosen} FROM vw_turnout;"
            return state

        # If user said "total votes" but not clear, return a safe helpful default
        if "total votes" in q_low or ("total" in q_low and "vote" in q_low):
            state.route = "sql"
            state.sql = "SELECT SUM(votants) AS total_votants FROM vw_turnout;"
            return state

    
    # 2) HYBRID: build SQL dynamically from resolved entities for analytics questions
    if is_analytics and state.resolved is not None:
        r = state.resolved

        # 2a) Seats queries (party seats)
        if ("seat" in q_low or "seats" in q_low or "siege" in q_low or "sieges" in q_low):
            # Try exact party if resolved
            if r.party:
                party = sql_str(r.party)
                # Also compute a "family key" from the first token of the party label (before '-' or space)
                # This generalizes to PDCI, RHDP, etc.
                fam = normalize_for_match(r.party)
                fam = re.split(r"[\s\-]+", fam)[0] if fam else ""

                if fam and len(fam) >= 3:
                    state.sql = (
                        "SELECT party, seats FROM vw_party_seats "
                        f"WHERE party = '{party}' OR lower(party) LIKE '%{sql_str(fam)}%' "
                        "ORDER BY seats DESC;"
                    )
                else:
                    state.sql = f"SELECT party, seats FROM vw_party_seats WHERE party = '{party}';"

                state.route = "sql"
                return state

            # If no party resolved, but user typed an acronym (P.D.C.I / R.H.D.P)
            ac = extract_acronym(q_norm)
            if ac:
                ac = ac.lower()
                state.sql = (
                    "SELECT party, seats FROM vw_party_seats "
                    f"WHERE lower(party) LIKE '%{sql_str(ac)}%' "
                    "ORDER BY seats DESC;"
                )
                state.route = "sql"
                return state

        # 2b) Winner queries by code/region/circonscription
        if ("winner" in q_low or "winners" in q_low or "who won" in q_low or "elu" in q_low):
            if r.circonscription_code:
                code = sql_str(r.circonscription_code)
                state.sql = (
                    "SELECT region, circonscription_code, circonscription_name, party, candidate, score "
                    "FROM vw_winners "
                    f"WHERE circonscription_code = '{code}';"
                )
                state.route = "sql"
                return state

            if r.region:
                region = sql_str(r.region)
                state.sql = (
                    "SELECT circonscription_code, circonscription_name, party, candidate, score "
                    "FROM vw_winners "
                    f"WHERE region = '{region}' "
                    "ORDER BY circonscription_code;"
                )
                state.route = "sql"
                return state

            if r.circonscription:
                circo = sql_str(r.circonscription)
                state.sql = (
                    "SELECT region, circonscription_code, circonscription_name, party, candidate, score "
                    "FROM vw_winners "
                    f"WHERE circonscription_name = '{circo}';"
                )
                state.route = "sql"
                return state

        # 2c) Turnout / participation queries by region or code
        if ("turnout" in q_low or "participation" in q_low):
            if r.circonscription_code:
                code = sql_str(r.circonscription_code)
                state.sql = (
                    "SELECT * FROM vw_turnout "
                    f"WHERE circonscription_code = '{code}';"
                )
                state.route = "sql"
                return state

            if r.region:
                region = sql_str(r.region)
                state.sql = (
                    "SELECT * FROM vw_turnout "
                    f"WHERE region = '{region}' "
                    "ORDER BY circonscription_code;"
                )
                state.route = "sql"
                return state

            # fallback: if user mentions a place name but resolver didn’t catch it, let RAG handle it
            # (will improve this in Level 3 disambiguation)

    # 3) If not handled by SQL/hybrid, route to RAG
    state.route = "rag"
    state.rag_query = q
    return state


def node_sql(state: L2State) -> L2State:
    assert state.sql is not None
    df, final_sql = run_query(Path(state.db_path), state.sql, limit=200)
    state.sql_used = final_sql
    state.sql_rows = df.to_dict(orient="records")
    return state


def node_rag(state: L2State) -> L2State:
    query = state.rag_query or state.user_query

    hits = retrieve(Path(state.db_path), query, k=5)
    state.rag_hits = [
        Citation(
            chunk_id=h.chunk_id,
            score=h.score,
            excerpt=h.excerpt,
            region=h.region,
            circonscription_code=h.circonscription_code,
            party=h.party,
            candidate=h.candidate,
        )
        for h in hits
    ]
    if not hits or hits[0].score < 2.0:   # tune threshold after observing typical values
        state.rag_hits = []
    return state


def node_compose(state: L2State) -> L2State:
    if state.route == "sql":
        base = answer_from_sql_local(state.sql_rows, state.sql_used or "")
        # SQL path doesn’t have RAG citations; still can enhance but with empty citations
        state.answer = enhance_with_openai_if_enabled(base, state.user_query, citations="")
        return state

    if state.route == "rag":
        base = answer_from_rag_local(state.user_query, state.rag_hits)
        cites = format_citations(state.rag_hits)
        state.answer = enhance_with_openai_if_enabled(base, state.user_query, citations=cites)
        return state

    if state.answer is None:
        state.answer = "**Not found in the provided PDF dataset.**"
    return state
