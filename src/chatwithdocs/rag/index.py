from __future__ import annotations

from pathlib import Path
import duckdb


def build_rag_index(
    db_path: Path,
    base_relation: str = "vw_results_clean",
    chunks_table: str = "rag_chunks",
) -> None:
    """
    Build a row-as-text RAG index inside DuckDB using the FTS extension.

    We create:
      - a rag_chunks table with stable chunk_id + chunk_text + metadata
      - an FTS index on chunk_text via PRAGMA create_fts_index
    """
    con = duckdb.connect(str(db_path))

    try:
        # Ensure FTS extension available + loaded
        con.execute("INSTALL fts;")
        con.execute("LOAD fts;")

        # Build chunks deterministically from the base relation
        con.execute(f"DROP TABLE IF EXISTS {chunks_table};")

        con.execute(
            f"""
            CREATE TABLE {chunks_table} AS
            SELECT
                row_number() OVER (
                    ORDER BY
                        circonscription_code,
                        party,
                        candidate,
                        score
                ) AS chunk_id,

                -- provenance fields
                region,
                circonscription_code,
                circonscription_name,
                party,
                candidate,
                score,
                score_percent,
                elected,
                nb_bv,
                inscrits,
                votants,
                taux_participation,
                bull_nuls,
                suf_exprimes,
                bull_blancs_nbr,
                bull_blancs_percent,

                -- retrieval text
                (
                  'region=' || region ||
                  ' | code=' || circonscription_code ||
                  ' | circo=' || circonscription_name ||
                  ' | party=' || party ||
                  ' | candidate=' || candidate ||
                  ' | score=' || CAST(score AS VARCHAR) ||
                  ' | score_percent=' || CAST(score_percent AS VARCHAR) ||
                  ' | elected=' || CAST(elected AS VARCHAR) ||
                  ' | inscrits=' || CAST(inscrits AS VARCHAR) ||
                  ' | votants=' || CAST(votants AS VARCHAR) ||
                  ' | suf_exprimes=' || CAST(suf_exprimes AS VARCHAR)
                ) AS chunk_text

            FROM {base_relation};
            """
        )

        # Drop and recreate index
        # DuckDB FTS creates schema fts_main_<table> and a macro match_bm25(...) for scoring.
        con.execute(
        f"PRAGMA create_fts_index('{chunks_table}', 'chunk_id', 'chunk_text', overwrite=1);"
        )


    finally:
        con.close()
