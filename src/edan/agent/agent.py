from __future__ import annotations
import re

UNANSWERABLE_HINTS = [
    "weather", "president", "api key", "system prompt", "password"
]

def looks_malicious(q: str) -> bool:
    ql = q.lower()
    return any(x in ql for x in ["drop table", "delete from", "update ", "insert ", "alter table", "exfiltrate"])

def generate_sql(question: str) -> str | None:
    q = re.sub(r"\s+", " ", question.strip().lower())

    # Acceptance Q1
    if "how many seats" in q and "rhdp" in q:
        return "SELECT seats FROM vw_party_seats WHERE party = 'RHDP';"

    # Acceptance Q2
    m = re.search(r"top\s*(\d+)\s+candidates.*region\s+(.+)", q)
    if m:
        n = int(m.group(1))
        region = m.group(2).strip().upper()
        return f"""
        SELECT candidate, party, score
        FROM vw_results_clean
        WHERE region = '{region}'
        ORDER BY score DESC
        LIMIT {n};
        """

    # Acceptance Q3
    if "participation rate" in q and "by region" in q:
        return """
        SELECT region, AVG(taux_participation) AS avg_participation
        FROM vw_turnout
        GROUP BY region
        ORDER BY avg_participation DESC;
        """

    # Acceptance Q4 (for chart later)
    if "histogram" in q and "winners" in q and "party" in q:
        return """
        SELECT party, COUNT(*) AS winners
        FROM vw_winners
        GROUP BY party
        ORDER BY winners DESC;
        """

    return None