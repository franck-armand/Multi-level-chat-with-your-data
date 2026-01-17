from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import duckdb


@dataclass
class RagHit:
    chunk_id: int
    score: float
    excerpt: str
    region: str
    circonscription_code: str
    party: str
    candidate: str


def retrieve(
    db_path: Path,
    query: str,
    k: int = 5,
    chunks_table: str = "rag_chunks",
) -> List[RagHit]:
    """
    Retrieve top-k chunks using DuckDB FTS BM25 score.

    DuckDB creates a macro like:
      fts_main_<table>.match_bm25(input_id, query_string, ...)
    """
    duckdb.connect().execute("INSTALL fts;")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("LOAD fts;")

        # fts schema name is fts_main_<table>
        fts_schema = f"fts_main_{chunks_table}"

        df = con.execute(
            f"""
            WITH ranked AS (
                SELECT
                    c.chunk_id,
                    c.region,
                    c.circonscription_code,
                    c.party,
                    c.candidate,
                    c.chunk_text,
                    {fts_schema}.match_bm25(c.chunk_id, ?) AS bm25
                FROM {chunks_table} c
            )
            SELECT
                chunk_id,
                region,
                circonscription_code,
                party,
                candidate,
                bm25 AS score,
                substr(chunk_text, 1, 220) AS excerpt
            FROM ranked
            WHERE score IS NOT NULL
            ORDER BY score DESC
            LIMIT ?;
            """,
            [query, k],
        ).df()

        hits: List[RagHit] = []
        for _, r in df.iterrows():
            hits.append(
                RagHit(
                    chunk_id=int(r["chunk_id"]),
                    score=float(r["score"]),
                    excerpt=str(r["excerpt"]),
                    region=str(r["region"]),
                    circonscription_code=str(r["circonscription_code"]),
                    party=str(r["party"]),
                    candidate=str(r["candidate"]),
                )
            )
        return hits
    finally:
        con.close()
