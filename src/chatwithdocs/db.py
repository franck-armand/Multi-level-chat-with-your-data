from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Literal

from .normalize import parse_int, parse_percent, clean_text
from chatwithdocs.sql.views import create_views
from chatwithdocs.rag.index import build_rag_index


def load_csv_to_sqlite(
    csv_path: Path,
    db_path: Path,
    table: str = "election_results",
    delimiter: str = ";",
) -> None:
    """Load the extracted CSV into SQLite.

    The table is replaced on each run for determinism.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.execute(
        f"""
        CREATE TABLE {table} (
            region TEXT,
            circonscription_code TEXT,
            circonscription_name TEXT,
            nb_bv INTEGER,
            inscrits INTEGER,
            votants INTEGER,
            taux_participation REAL,
            bull_nuls INTEGER,
            suf_exprimes INTEGER,
            bull_blancs_nbr INTEGER,
            bull_blancs_percent REAL,
            party TEXT,
            candidate TEXT,
            score INTEGER,
            score_percent REAL,
            elected INTEGER
        )
        """
    )

    to_insert = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for r in reader:
            to_insert.append(
                (
                    clean_text(r["region"]),
                    clean_text(r["circonscription_code"]),
                    clean_text(r["circonscription_name"]),
                    parse_int(r["nb_bv"]),
                    parse_int(r["inscrits"]),
                    parse_int(r["votants"]),
                    parse_percent(r["taux_participation"]),
                    parse_int(r["bull_nuls"]),
                    parse_int(r["suf_exprimes"]),
                    parse_int(r["bull_blancs_nbr"]),
                    parse_percent(r["bull_blancs_percent"]),
                    clean_text(r["party"]),
                    clean_text(r["candidate"]),
                    parse_int(r["score"]),
                    parse_percent(r["score_percent"]),
                    1 if str(r["elected"]).lower() in {"1", "true", "yes"} else 0,
                )
            )

    cur.executemany(
        f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        to_insert,
    )
    conn.commit()
    conn.close()


def load_csv_to_duckdb(
    csv_path: Path,
    db_path: Path,
    table: str = "election_results",
    delimiter: str = ";",
) -> None:
    """Load the extracted CSV into DuckDB."""
    try:
        import duckdb  # type: ignore
    except Exception as e: 
        raise RuntimeError(
            "DuckDB is not installed. Install with: uv pip install duckdb"
        ) from e

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(db_path))
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(
        f"""
        CREATE TABLE {table} (
            region VARCHAR,
            circonscription_code VARCHAR,
            circonscription_name VARCHAR,
            nb_bv INTEGER,
            inscrits INTEGER,
            votants INTEGER,
            taux_participation DOUBLE,
            bull_nuls INTEGER,
            suf_exprimes INTEGER,
            bull_blancs_nbr INTEGER,
            bull_blancs_percent DOUBLE,
            party VARCHAR,
            candidate VARCHAR,
            score INTEGER,
            score_percent DOUBLE,
            elected BOOLEAN
        )
        """
    )

    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for r in reader:
            rows.append(
                (
                    clean_text(r["region"]),
                    clean_text(r["circonscription_code"]),
                    clean_text(r["circonscription_name"]),
                    parse_int(r["nb_bv"]),
                    parse_int(r["inscrits"]),
                    parse_int(r["votants"]),
                    parse_percent(r["taux_participation"]),
                    parse_int(r["bull_nuls"]),
                    parse_int(r["suf_exprimes"]),
                    parse_int(r["bull_blancs_nbr"]),
                    parse_percent(r["bull_blancs_percent"]),
                    clean_text(r["party"]),
                    clean_text(r["candidate"]),
                    parse_int(r["score"]),
                    parse_percent(r["score_percent"]),
                    str(r["elected"]).lower() in {"1", "true", "yes"},
                )
            )

    conn.executemany(
        f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    
    # Create views
    create_views(conn, table=table)
    
    # Build FTS index
    build_rag_index(db_path)
    
    conn.close()


def load_csv_to_db(
    csv_path: Path,
    db_path: Path,
    table: str = "election_results",
    delimiter: str = ";",
    engine: Literal["duckdb", "sqlite"] = "duckdb",
) -> None:
    """Convenience wrapper."""
    if engine == "duckdb":
        load_csv_to_duckdb(csv_path, db_path, table=table, delimiter=delimiter)
    elif engine == "sqlite":
        load_csv_to_sqlite(csv_path, db_path, table=table, delimiter=delimiter)
    else:  
        raise ValueError(f"Unsupported engine: {engine}")
