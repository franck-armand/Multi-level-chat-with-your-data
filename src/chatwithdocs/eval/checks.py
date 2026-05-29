from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CheckResult:
    ok: bool
    reason: str = ""


def _contains_all(text: str, needles: List[str]) -> bool:
    t = (text or "").lower()
    return all(n.lower() in t for n in needles)


def check_answer_contains(answer: str, needles: List[str]) -> CheckResult:
    if not needles:
        return CheckResult(True)
    if _contains_all(answer, needles):
        return CheckResult(True)
    return CheckResult(False, f"answer missing required strings: {needles}")


def check_route(route: str, allowed: List[str]) -> CheckResult:
    if not allowed:
        return CheckResult(True)
    if route in allowed:
        return CheckResult(True)
    return CheckResult(False, f"route='{route}' not in {allowed}")


def check_sql_contains(sql_used: str, needles: List[str]) -> CheckResult:
    if not needles:
        return CheckResult(True)
    sql = (sql_used or "").lower()
    missing = [n for n in needles if n.lower() not in sql]
    if not missing:
        return CheckResult(True)
    return CheckResult(False, f"sql missing required substrings: {missing}")


def check_min_citations(citations: List[Dict[str, Any]], min_n: int) -> CheckResult:
    if min_n <= 0:
        return CheckResult(True)
    if len(citations) >= min_n:
        return CheckResult(True)
    return CheckResult(False, f"expected at least {min_n} citations, got {len(citations)}")


def check_citations_contain(citations: List[Dict[str, Any]], needles: List[str]) -> CheckResult:
    """
    Loose faithfulness: ensure cited excerpts contain required strings.
    """
    if not needles:
        return CheckResult(True)
    excerpts = " ".join([(c.get("excerpt") or "") for c in citations]).lower()
    missing = [n for n in needles if n.lower() not in excerpts]
    if not missing:
        return CheckResult(True)
    return CheckResult(False, f"citations excerpts missing: {missing}")


def check_oracle_numeric(
    assistant_value: Any,
    oracle_value: Any,
    tolerance: float = 0.0,
) -> CheckResult:
    """
    Compare assistant numeric output to oracle numeric output (exact/tolerance).
    assistant_value / oracle_value are already extracted numbers.
    """
    if assistant_value is None:
        return CheckResult(False, "assistant numeric value is None")
    if oracle_value is None:
        return CheckResult(False, "oracle numeric value is None")

    try:
        a = float(assistant_value)
        o = float(oracle_value)
    except Exception:
        return CheckResult(
            False, f"could not cast to float: assistant={assistant_value}, oracle={oracle_value}"
        )

    if abs(a - o) <= float(tolerance):
        return CheckResult(True)
    return CheckResult(False, f"numeric mismatch: assistant={a}, oracle={o}, tol={tolerance}")


def extract_first_number(text: str) -> Optional[float]:
    m = re.search(r"(-?\d+(?:\.\d+)?)", text or "")
    if not m:
        return None
    return float(m.group(1))
