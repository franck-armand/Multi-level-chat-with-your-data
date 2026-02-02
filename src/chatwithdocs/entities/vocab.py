from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List
import duckdb


@dataclass(frozen=True)
class Vocab:
    regions: List[str]
    parties: List[str]
    circo_names: List[str]
    candidates: List[str]


def load_vocab(db_path: Path) -> Vocab:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        regions = con.execute("SELECT DISTINCT region FROM vw_turnout ORDER BY 1").fetchall()
        parties = con.execute("SELECT DISTINCT party FROM vw_results_clean ORDER BY 1").fetchall()
        circo_names = con.execute("SELECT DISTINCT circonscription_name FROM vw_turnout ORDER BY 1").fetchall()
        candidates = con.execute("SELECT DISTINCT candidate FROM vw_results_clean ORDER BY 1").fetchall()
    finally:
        con.close()

    return Vocab(
        regions=[r[0] for r in regions if r[0]],
        parties=[p[0] for p in parties if p[0]],
        circo_names=[c[0] for c in circo_names if c[0]],
        candidates=[c[0] for c in candidates if c[0]],
    )
