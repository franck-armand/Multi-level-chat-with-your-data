from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Choice:
    key: str # stable key (e.g. "region:DISTRICT AUTONOME D'ABIDJAN")
    label: str # shown to user
    payload: Dict[str, Any] # how to apply (e.g. {"region": "..."} or {"circo_code": "181"})


@dataclass
class L3State:
    user_query: str
    db_path: str

    # session memory (passed from Streamlit)
    memory: Dict[str, Any] = field(default_factory=dict)

    # set when clarification is needed
    pending: bool = False
    clarify_question: Optional[str] = None
    choices: List[Choice] = field(default_factory=list)

    # final answer (plain text)
    answer: Optional[str] = None
