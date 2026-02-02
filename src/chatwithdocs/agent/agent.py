from __future__ import annotations

import re
from .types import QueryPlan


def looks_malicious(q: str) -> bool:
    ql = q.lower()
    bad = [
        # SQL destructive/exfil
        "drop table", "delete from", "update ", "insert ", "alter table",
        "exfiltrate", "attach ", "copy ", "pragma",
        # prompt/key exfil
        "system prompt", "api key", "api keys", "secret", "password", "token",
        "print environment", "env var"
    ]
    return any(x in ql for x in bad)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _detect_chart(q: str) -> tuple[str | None, str]:
    """Returns (chart_type, normalized_text_without_chart_words)."""
    ql = q.lower()
    chart_type = None
    if "pie" in ql:
        chart_type = "pie"
    elif "histogram" in ql or "distribution" in ql:
        chart_type = "hist"
    elif "bar chart" in ql or ("bar" in ql and "chart" in ql):
        chart_type = "bar"

    # strip common chart words for easier intent matching
    cleaned = re.sub(r"\b(bar chart|pie chart|histogram|chart|plot|graph)\b", "", ql)
    cleaned = _norm(cleaned)
    return chart_type, cleaned


def _extract_region(q_clean: str) -> str | None:
    m = re.search(r"\bregion\s+([a-z0-9\-\s]+)$", q_clean, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().upper()


def _extract_top_n(q_clean: str, default: int = 10) -> int:
    m = re.search(r"\btop\s+(\d+)\b", q_clean)
    return int(m.group(1)) if m else default


def _extract_code(q_clean: str) -> str | None:
    m = re.search(r"\bcode\s+(\d{1,3})\b", q_clean)
    if not m:
        return None
    return m.group(1).zfill(3)


def plan_question(question: str) -> QueryPlan | None:
    q_raw = _norm(question)
    chart_type, q = _detect_chart(q_raw)

    # ---------- Seats ----------
    if "seats" in q or "sieges" in q:
        # RHDP seats
        if "rhdp" in q:
            return QueryPlan(
                intent="table",
                sql="SELECT seats FROM vw_party_seats WHERE party = 'RHDP';",
                narrative="Seats won by RHDP:"
            )

        # seats by party
        if "each party" in q or "by party" in q or "par parti" in q:
            sql = "SELECT party, seats FROM vw_party_seats ORDER BY seats DESC;"
            if chart_type in {"bar", "pie"}:
                return QueryPlan(
                    intent="chart",
                    chart_type=chart_type,
                    sql=sql,
                    x="party",
                    y="seats",
                    title="Seats by party",
                    narrative="Seats by party:"
                )
            return QueryPlan(intent="table", sql=sql, narrative="Seats by party:")

        # parties with at least N seats
        m = re.search(r"at least\s+(\d+)\s+seats", q)
        if m:
            n = int(m.group(1))
            sql = f"SELECT party, seats FROM vw_party_seats WHERE seats >= {n} ORDER BY seats DESC;"
            return QueryPlan(intent="table", sql=sql, narrative=f"Parties with at least {n} seats:")

    # ---------- Winners ----------
    if "winner" in q or "winners" in q or "elu" in q:
        region = _extract_region(q)
        code = _extract_code(q)

        if code:
            sql = f"""
            SELECT region, circonscription_code, circonscription_name, party, candidate, score
            FROM vw_winners
            WHERE circonscription_code = '{code}';
            """
            return QueryPlan(intent="table", sql=sql, narrative=f"Winner for circonscription code {code}:")

        if region:
            sql = f"""
            SELECT circonscription_code, circonscription_name, party, candidate, score
            FROM vw_winners
            WHERE region = '{region}'
            ORDER BY circonscription_code;
            """
            return QueryPlan(intent="table", sql=sql, narrative=f"Winners in region {region}:")

        # winners by party (counts) -> chart/table
        if "by party" in q or "par parti" in q:
            sql = """
            SELECT party, COUNT(*) AS winners
            FROM vw_winners
            GROUP BY party
            ORDER BY winners DESC;
            """
            if chart_type in {"bar", "pie"}:
                return QueryPlan(
                    intent="chart",
                    chart_type=chart_type,
                    sql=sql,
                    x="party",
                    y="winners",
                    title="Winners by party",
                    narrative="Winners by party:"
                )
            # default: bar-like table
            return QueryPlan(intent="table", sql=sql, narrative="Winners by party:")

    # ---------- Participation / turnout ----------
    if "participation" in q or "turnout" in q:
        # by region
        if "by region" in q:
            sql = """
            SELECT region, AVG(taux_participation) AS avg_participation
            FROM vw_turnout
            GROUP BY region
            ORDER BY avg_participation DESC;
            """
            if chart_type in {"bar"}:
                return QueryPlan(
                    intent="chart",
                    chart_type="bar",
                    sql=sql,
                    x="region",
                    y="avg_participation",
                    title="Average participation rate by region",
                    narrative="Participation rate by region:"
                )
            return QueryPlan(intent="table", sql=sql, narrative="Participation rate by region:")

        # top N circonscriptions by turnout
        if "circonscription" in q and ("top" in q or "highest" in q):
            n = _extract_top_n(q, default=5)
            sql = f"""
            SELECT region, circonscription_code, circonscription_name, taux_participation
            FROM vw_turnout
            ORDER BY taux_participation DESC
            LIMIT {n};
            """
            return QueryPlan(intent="table", sql=sql, narrative=f"Top {n} circonscriptions by turnout rate:")

    # ---------- Top candidates ----------
    if "top" in q and "candidate" in q:
        n = _extract_top_n(q, default=10)
        region = _extract_region(q)
        if region:
            sql = f"""
            SELECT candidate, party, score
            FROM vw_results_clean
            WHERE region = '{region}'
            ORDER BY score DESC
            LIMIT {n};
            """
            return QueryPlan(intent="table", sql=sql, narrative=f"Top {n} candidates by score in region {region}:")

        # global
        sql = f"""
        SELECT candidate, party, region, score
        FROM vw_results_clean
        ORDER BY score DESC
        LIMIT {n};
        """
        return QueryPlan(intent="table", sql=sql, narrative=f"Top {n} candidates overall by score:")

    # ---------- Votes by party ----------
    if "total votes" in q or ("votes" in q and "party" in q and "top" in q):
        n = _extract_top_n(q, default=10)
        sql = f"""
        SELECT party, SUM(score) AS total_votes
        FROM vw_results_clean
        GROUP BY party
        ORDER BY total_votes DESC
        LIMIT {n};
        """
        if chart_type in {"bar", "pie"}:
            return QueryPlan(
                intent="chart",
                chart_type=chart_type,
                sql=sql,
                x="party",
                y="total_votes",
                title=f"Top {n} parties by total votes",
                narrative=f"Top {n} parties by total votes:"
            )
        return QueryPlan(intent="table", sql=sql, narrative=f"Top {n} parties by total votes:")

    # ---------- Histogram of candidate scores ----------
    if chart_type == "hist" and "score" in q:
        region = _extract_region(q)
        if region:
            sql = f"SELECT score FROM vw_results_clean WHERE region = '{region}';"
            return QueryPlan(
                intent="chart",
                chart_type="hist",
                sql=sql,
                x=None,
                y="score",
                title=f"Score distribution in region {region}",
                narrative=f"Histogram of candidate scores in region {region}:"
            )
        sql = "SELECT score FROM vw_results_clean;"
        return QueryPlan(
            intent="chart",
            chart_type="hist",
            sql=sql,
            x=None,
            y="score",
            title="Score distribution (all candidates)",
            narrative="Histogram of candidate scores:"
        )

    return None
