from __future__ import annotations
from pathlib import Path
import duckdb

from .safe import validate_sql, enforce_limit

ALLOWED_RELATIONS = {
    "vw_results_clean",
    "vw_turnout",
    "vw_winners",
    "vw_party_seats",
    "election_results",
}

def run_query(db_path: Path, sql: str, limit: int = 200):
    sql = validate_sql(sql, ALLOWED_RELATIONS)
    sql = enforce_limit(sql, limit=limit)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(sql).df()
    finally:
        con.close()
    return df, sql
