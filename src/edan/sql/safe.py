from __future__ import annotations
import re

DENYLIST = [
    "insert", "update", "delete", "drop", "alter", "create", "attach", "detach",
    "copy", "pragma", "vacuum", "export", "import", "call"
]

SELECT_PREFIX = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

def enforce_limit(sql: str, limit: int = 200) -> str:
    # If query already has LIMIT, keep it. Otherwise append one.
    if re.search(r"\blimit\s+\d+", sql, re.IGNORECASE):
        return sql
    return sql.rstrip().rstrip(";") + f"\nLIMIT {limit};"

def validate_sql(sql: str, allowed_relations: set[str]) -> str:
    s = sql.strip()
    low = s.lower()

    # Must be single statement
    if ";" in s.strip().rstrip(";"):
        raise ValueError("Only single-statement SQL is allowed.")

    # Must be SELECT/WITH
    if not SELECT_PREFIX.match(s):
        raise ValueError("Only SELECT/WITH queries are allowed.")

    # Denylist
    for kw in DENYLIST:
        if re.search(rf"\b{re.escape(kw)}\b", low):
            raise ValueError(f"Forbidden SQL keyword detected: {kw}")

    # Basic relation allowlist check: FROM/JOIN targets must be allowed, maybe upgrade to sqllot later ? I will see
    rels = set(re.findall(r"\bfrom\s+([a-zA-Z_][\w]*)|\bjoin\s+([a-zA-Z_][\w]*)", low))
    flat = set()
    for a,b in rels:
        if a: flat.add(a)
        if b: flat.add(b)

    for r in flat:
        if r not in {x.lower() for x in allowed_relations}:
            raise ValueError(f"Relation not allowed: {r}")

    return s
