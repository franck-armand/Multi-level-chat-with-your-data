from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from edan.entities.resolve import Resolved


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
    # input
    user_query: str
    db_path: str

    # resolved entities
    resolved: Optional[Resolved] = None

    # router decision
    route: Optional[str] = None  # "sql" | "rag" | "hybrid"

    # SQL path
    sql: Optional[str] = None
    sql_used: Optional[str] = None
    sql_rows: Optional[List[Dict[str, Any]]] = None

    # RAG path
    rag_query: Optional[str] = None
    rag_hits: List[Citation] = field(default_factory=list)

    # output
    answer: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
