from __future__ import annotations

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

    if looks_malicious(q):
        state.route = "blocked"
        state.answer = (
            "I can't help with destructive or exfiltration requests. "
            "Ask an analytics question about the dataset instead."
        )
        return state

    # If Level 1 planner can handle it, route to SQL
    plan = plan_question(q)
    
    # Hybrid: if we resolved a party and user asks about seats, answer via SQL
    q_low = q.lower()
    if state.resolved and state.resolved.party and ("seat" in q_low or "seats" in q_low or "siege" in q_low or "sieges" in q_low):
        state.route = "sql"
        party = state.resolved.party.replace("'", "''")
        state.sql = f"SELECT party, seats FROM vw_party_seats WHERE party = '{party}';"
        return state

    if plan is not None:
        state.route = "sql"
        state.sql = plan.sql
        return state

    # Otherwise route to RAG
    # Also: if we detected some entity but planner doesn't have template, RAG can still help.
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
