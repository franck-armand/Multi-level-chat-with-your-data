from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TraceEvent:
    name: str
    t0_ms: int
    t1_ms: int
    ms: int
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class Trace:
    trace_id: str
    ts_start_ms: int
    ts_end_ms: Optional[int] = None
    total_ms: Optional[int] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    events: List[TraceEvent] = field(default_factory=list)

    def finish(self) -> None:
        self.ts_end_ms = int(time.time() * 1000)
        self.total_ms = self.ts_end_ms - self.ts_start_ms

    def to_dict(self) -> Dict[str, Any]:
        def event_to_dict(e: Any) -> Dict[str, Any]:
            # If it's already a dict, accept it
            if isinstance(e, dict):
                return e

            # If it looks like a TraceEvent (has attributes), serialize safely
            name = getattr(e, "name", None)
            if name is not None:
                return {
                    "name": getattr(e, "name", "unknown"),
                    "t0_ms": getattr(e, "t0_ms", 0),
                    "t1_ms": getattr(e, "t1_ms", 0),
                    "ms": getattr(e, "ms", 0),
                    "data": getattr(e, "data", {}) or {},
                    "error": getattr(e, "error", None),
                }

            # Fallback for anything unexpected
            return {
                "name": "unknown_event",
                "t0_ms": 0,
                "t1_ms": 0,
                "ms": 0,
                "data": {"repr": repr(e)},
                "error": None,
            }

        return {
            "trace_id": self.trace_id,
            "ts_start_ms": self.ts_start_ms,
            "ts_end_ms": self.ts_end_ms,
            "total_ms": self.total_ms,
            "meta": self.meta,
            "events": [event_to_dict(e) for e in self.events],
        }


def new_trace(meta: Optional[Dict[str, Any]] = None) -> Trace:
    return Trace(
        trace_id=str(uuid.uuid4()),
        ts_start_ms=int(time.time() * 1000),
        meta=meta or {},
    )


@contextmanager
def trace_event(trace: Trace, name: str, data: Optional[Dict[str, Any]] = None):
    t0 = int(time.time() * 1000)
    err = None
    try:
        yield
    except Exception as e:
        err = str(e)
        raise
    finally:
        t1 = int(time.time() * 1000)
        trace.events.append(
            TraceEvent(
                name=name,
                t0_ms=t0,
                t1_ms=t1,
                ms=t1 - t0,
                data=data or {},
                error=err,
            )
        )
