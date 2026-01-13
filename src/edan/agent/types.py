from dataclasses import dataclass
from typing import Optional

@dataclass
class QueryPlan:
    intent: str # table, chart
    sql: str
    chart_type: Optional[str] = None  # bar, hist, pie
    x: Optional[str] = None
    y: Optional[str] = None
    title: Optional[str] = None
    narrative: Optional[str] = None
