from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import duckdb

from chatwithdocs.eval.checks import (
    check_answer_contains,
    check_route,
    check_sql_contains,
    check_min_citations,
    check_citations_contain,
    check_oracle_numeric,
    extract_first_number,
)
from chatwithdocs.level2.graph import run_level2
from chatwithdocs.level3.graph import run_level3
from chatwithdocs.obs.trace import Trace


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _trace_excerpt(trace: Trace | None, max_events: int = 12) -> Dict[str, Any] | None:
    if not trace:
        return None
    d = trace.to_dict()
    return {
        "trace_id": d.get("trace_id"),
        "total_ms": d.get("total_ms"),
        "meta": d.get("meta", {}),
        "events": d.get("events", [])[:max_events],
    }


def _extract_citations_from_state(state: Any) -> List[Dict[str, Any]]:
    hits = getattr(state, "rag_hits", None)
    if not hits:
        return []
    out = []
    for h in hits:
        out.append({
            "chunk_id": getattr(h, "chunk_id", None),
            "score": getattr(h, "score", None),
            "excerpt": getattr(h, "excerpt", ""),
            "region": getattr(h, "region", None),
            "circonscription_code": getattr(h, "circonscription_code", None),
            "party": getattr(h, "party", None),
            "candidate": getattr(h, "candidate", None),
        })
    return out


def _oracle_query(db_path: Path, oracle_sql: str) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        res = con.execute(oracle_sql)
        cols = [c[0] for c in res.description]
        rows = res.fetchall()
        return cols, rows
    finally:
        con.close()


def _oracle_single_value(db_path: Path, oracle_sql: str, oracle_column: str | None = None) -> Any:
    cols, rows = _oracle_query(db_path, oracle_sql)
    if not rows:
        return None
    first = rows[0]
    if oracle_column:
        if oracle_column not in cols:
            raise ValueError(f"oracle_column '{oracle_column}' not in oracle cols {cols}")
        idx = cols.index(oracle_column)
        return first[idx]
    # if not specified, take first column
    return first[0] if first else None


def run_eval(db_path: Path, suite_path: Path, out_dir: Path) -> None:
    _ensure_dir(out_dir)

    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    tests: List[Dict[str, Any]] = suite["tests"]

    failures_path = out_dir / "level4_failures.jsonl"
    summary_path = out_dir / "level4_summary.json"
    traces_out = out_dir / "traces.jsonl"

    total = 0
    passed = 0
    failures: List[Dict[str, Any]] = []
    route_counts: Dict[str, int] = {}
    latencies: List[int] = []

    for t in tests:
        total += 1
        tid = t["id"]
        mode = t.get("mode", "level2")
        query = t["query"]
        expect = t.get("expect", {})

        try:
            if mode == "level2":
                state = run_level2(query, str(db_path), trace_out=str(traces_out))
                route = getattr(state, "route", None) or "unknown"
                answer = getattr(state, "answer", "") or ""
                sql_used = getattr(state, "sql_used", "") or ""
                citations = _extract_citations_from_state(state)
                trace = getattr(state, "trace", None)

            elif mode == "level3":
                state = run_level3(query, str(db_path), memory={}, trace_out=str(traces_out))
                # Level 3 route proxy
                route = "clarify" if getattr(state, "pending", False) else "delegated"
                answer = getattr(state, "answer", "") or ""
                sql_used = ""
                citations = []
                trace = getattr(state, "trace", None)

            else:
                raise ValueError(f"Unknown mode: {mode}")

            route_counts[route] = route_counts.get(route, 0) + 1
            if trace and trace.total_ms is not None:
                latencies.append(int(trace.total_ms))

            checks = []
            checks.append(check_route(route, expect.get("route_in", [])))
            checks.append(check_answer_contains(answer, expect.get("answer_contains", [])))
            checks.append(check_sql_contains(sql_used, expect.get("sql_contains", [])))
            checks.append(check_min_citations(citations, int(expect.get("min_citations", 0))))
            checks.append(check_citations_contain(citations, expect.get("citations_must_contain", [])))

            # ORACLE numeric correctness (recommended for aggregations)
            # If oracle_sql present, we compare assistant output vs oracle
            if "oracle_sql" in expect:
                oracle_sql = expect["oracle_sql"]
                oracle_column = expect.get("oracle_column")
                tolerance = float(expect.get("tolerance", 0.0))

                oracle_val = _oracle_single_value(db_path, oracle_sql, oracle_column)

                # assistant numeric extraction:
                # - prefer 1st number from answer text
                # - fallback: if SQL route and sql_rows exists, use the first cell (if present)
                assistant_val = None

                sql_rows = getattr(state, "sql_rows", None)
                if sql_rows and isinstance(sql_rows, list) and len(sql_rows) > 0:
                    row0 = sql_rows[0]
                    if oracle_column and oracle_column in row0:
                        assistant_val = row0[oracle_column]
                    else:
                        # fallback: first column in the first row
                        if isinstance(row0, dict) and len(row0) > 0:
                            assistant_val = next(iter(row0.values()))

                # fallback: parse from answer text only if no sql_rows available
                if assistant_val is None:
                    assistant_val = extract_first_number(answer)

                checks.append(check_oracle_numeric(assistant_val, oracle_val, tolerance=tolerance))

            bad = [c for c in checks if not c.ok]
            if bad:
                failures.append({
                    "id": tid,
                    "mode": mode,
                    "query": query,
                    "reasons": [b.reason for b in bad if b.reason],
                    "answer": answer[:3000],
                    "sql_used": sql_used[:2000],
                    "citations": citations[:5],
                    "trace_excerpt": _trace_excerpt(trace),
                })
            else:
                passed += 1

        except Exception as e:
            failures.append({
                "id": tid,
                "mode": mode,
                "query": query,
                "reasons": [f"exception: {e}"],
                "trace_excerpt": None,
            })

    with failures_path.open("w", encoding="utf-8") as f:
        for x in failures:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    lat_sorted = sorted(latencies)
    summary = {
        "suite": str(suite_path),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 0.0,
        "route_counts": route_counts,
        "latency_ms": {
            "count": len(latencies),
            "avg": (sum(latencies) / len(latencies)) if latencies else None,
            "p50": (lat_sorted[len(lat_sorted)//2] if lat_sorted else None),
            "p95": (lat_sorted[max(0, int(0.95*len(lat_sorted))-1)] if lat_sorted else None),
            "max": (max(latencies) if latencies else None),
        },
        "failures_file": str(failures_path),
        "traces_file": str(traces_out),
    }

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Level 4 Eval Summary ===")
    print(f"Suite: {suite_path}")
    print(f"Passed: {passed}/{total} ({summary['pass_rate']:.2%})")
    print(f"Failures: {failures_path}")
    print(f"Traces: {traces_out}")