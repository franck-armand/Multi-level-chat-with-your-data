from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .trace import Trace


class JsonlTraceSink:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, trace: Trace) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
