from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from chatwithdocs.obs.trace import Trace


@dataclass
class Citation:
    chunk_id: int
    score: float
    excerpt: str
    region: str
    circonscription_code: str
    party: str
    candidate: str


@dataclass
class L2State:
    user_query: str
    db_path: str

    # Resolved entities / router
    resolved: Any | None = None
    route: str | None = None  # "sql" | "rag" | "hybrid" | "blocked"

    # SQL path
    sql: str | None = None
    sql_used: str | None = None
    sql_rows: List[Dict[str, Any]] | None = None

    # RAG path
    rag_query: str | None = None
    rag_hits: List[Citation] = field(default_factory=list)

    # Output
    answer: str | None = None
    warnings: List[str] = field(default_factory=list)

    # Tracing
    trace: Trace | None = None
