from __future__ import annotations
from pathlib import Path
import duckdb

from .safe import validate_sql, enforce_limit
from edan.obs.trace import Trace, trace_event

ALLOWED_RELATIONS = {
    "election_results",
    "vw_results_clean",
    "vw_turnout",
    "vw_winners",
    "vw_party_seats",
}

def run_query(db_path: Path, sql: str, limit: int = 200, trace: Trace | None = None):
    # Validate
    if trace:
        with trace_event(trace, "sql.validate", {"sql": sql[:500]}):
            sql_validated = validate_sql(sql, ALLOWED_RELATIONS)
    else:
        sql_validated = validate_sql(sql, ALLOWED_RELATIONS)

    final_sql = enforce_limit(sql_validated, limit=limit)

    # Execute
    if trace:
        with trace_event(trace, "sql.execute", {"limit": limit}):
            con = duckdb.connect(str(db_path), read_only=True)
            try:
                df = con.execute(final_sql).df()
            finally:
                con.close()
        # Record result shape
        if trace:
            with trace_event(trace, "sql.result", {"rows": int(len(df)), "cols": list(df.columns)}):
                pass

    else:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            df = con.execute(final_sql).df()
        finally:
            con.close()

    if trace:
        # lightweight event for row/col count
        with trace_event(trace, "sql.result", {"rows": int(len(df)), "cols": list(df.columns)}):
            pass

    return df, final_sql
