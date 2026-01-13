from __future__ import annotations

import argparse
from pathlib import Path

from .extract_docx import extract_docx_to_csv
from .validate import run_validations
from .db import load_csv_to_db
from .agent.agent import plan_question, looks_malicious
from .sql.exec import run_query

def main() -> None:
    p = argparse.ArgumentParser(prog="edan", description="EDAN 2025 extraction + validation + DB utilities")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="Extract structured dataset from DOCX into semicolon CSV")
    p_extract.add_argument("--docx", required=True, type=Path, help="Path to EDAN_2025_RESULTAT_NATIONAL_DETAILS.docx")
    p_extract.add_argument("--out", required=True, type=Path, help="Output CSV path")
    p_extract.add_argument("--delimiter", default=";", help="CSV delimiter (default: ;)")

    p_val = sub.add_parser("validate", help="Run validation suite on produced CSV")
    p_val.add_argument("--csv", required=True, type=Path, help="Path to extracted CSV")
    p_val.add_argument("--delimiter", default=";", help="CSV delimiter (default: ;)")

    p_db = sub.add_parser("load-db", help="Load CSV into SQLite for Level-1 SQL agent")
    p_db.add_argument("--csv", required=True, type=Path, help="Input CSV")
    p_db.add_argument("--db", required=True, type=Path, help="SQLite DB path")
    p_db.add_argument("--table", default="election_results", help="Table name")
    p_db.add_argument("--delimiter", default=";", help="CSV delimiter (default: ;)")
    p_db.add_argument("--engine", choices=["duckdb", "sqlite"], default="duckdb", help="DB engine")
    
    p_ask = sub.add_parser("ask", help="Ask a question (intent->SQL->safe exec) against the DuckDB")
    p_ask.add_argument("--db", required=True, type=Path, help="DuckDB path")
    p_ask.add_argument("--q", required=True, help="User question")
    p_ask.add_argument("--limit", type=int, default=200, help="Max rows to return")

    args = p.parse_args()

    if args.cmd == "extract":
        extract_docx_to_csv(args.docx, args.out, delimiter=args.delimiter)
        print(f"[OK] Wrote CSV: {args.out}")
    elif args.cmd == "validate":
        run_validations(args.csv, delimiter=args.delimiter)
        print("[OK] Validation passed")
    elif args.cmd == "load-db":
        load_csv_to_db(
            args.csv,
            args.db,
            table=args.table,
            delimiter=args.delimiter,
            engine=args.engine,
        )
        print(f"[OK] Loaded DB: {args.db} (engine: {args.engine}, table: {args.table})")
    elif args.cmd == "ask":
        if looks_malicious(args.q):
            print("Refused: unsafe request (destructive or exfiltration attempt).")
            return

        plan = plan_question(args.q)
        if not plan:
            print("Not found in the provided PDF dataset.")
            print("Tip: ask about seats, rankings, participation rates, winners by party, etc.")
            return

        df, final_sql = run_query(args.db, plan.sql, limit=args.limit)

        print("*" * 30)
        if plan.narrative:
            print(plan.narrative)
        print("SQL used:\n", final_sql)
        print("\nResult preview:")
        print(df.head(20).to_string(index=False))
        print("*" * 30)

 