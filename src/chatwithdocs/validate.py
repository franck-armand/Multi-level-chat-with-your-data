from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .normalize import parse_int, parse_percent


class ValidationError(RuntimeError):
    pass


def run_validations(csv_path: Path, delimiter: str = ";") -> None:
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for r in reader:
            rows.append(r)

    if not rows:
        raise ValidationError("CSV is empty")

    required = {
        "region","circonscription_code","circonscription_name",
        "nb_bv","inscrits","votants","taux_participation",
        "bull_nuls","suf_exprimes","bull_blancs_nbr","bull_blancs_percent",
        "party","candidate","score","score_percent","elected",
    }
    missing = required - set(rows[0].keys())
    if missing:
        raise ValidationError(f"Missing columns: {sorted(missing)}")

    bad_tokens = ["NB BV", "REGI", "CIRCONSCRIPTION", "BULL. BLANCS", "SUF. EXPRIMES"]
    for r in rows:
        name = r["circonscription_name"].upper()
        if any(tok in name for tok in bad_tokens):
            raise ValidationError(
                f"Header bleed detected in circonscription_name for code={r['circonscription_code']}: {r['circonscription_name']}"
            )

    empties = [r for r in rows if not r["circonscription_name"].strip()]
    if empties:
        raise ValidationError(f"Found {len(empties)} rows with empty circonscription_name")

    numeric_cols = ["nb_bv","inscrits","votants","bull_nuls","suf_exprimes","bull_blancs_nbr","score"]
    for r in rows:
        for col in numeric_cols:
            v = parse_int(r[col])
            if v is None:
                raise ValidationError(f"Non-numeric {col} for code={r['circonscription_code']}: {r[col]}")
        if parse_percent(r["taux_participation"]) is None:
            raise ValidationError(f"Bad taux_participation for code={r['circonscription_code']}: {r['taux_participation']}")
        if parse_percent(r["score_percent"]) is None:
            raise ValidationError(f"Bad score_percent for code={r['circonscription_code']}: {r['score_percent']}")

    by_code = defaultdict(list)
    for r in rows:
        by_code[r["circonscription_code"]].append(r)

    for code, grp in by_code.items():
        votants = max(parse_int(x["votants"]) for x in grp)
        suf = max(parse_int(x["suf_exprimes"]) for x in grp)
        nuls = max(parse_int(x["bull_nuls"]) for x in grp)
        if (suf + nuls) != votants:
            raise ValidationError(f"Vote identity failed for code={code}: suf({suf}) + nuls({nuls}) != votants({votants})")

    # SUF_EXPRIMES must equal sum(candidate scores) + bull_blancs_nbr
    mismatches = []
    for code, grp in by_code.items():
        suf = max(parse_int(x["suf_exprimes"]) for x in grp)
        blancs = max(parse_int(x["bull_blancs_nbr"]) for x in grp)
        total = sum(parse_int(x["score"]) for x in grp)

        if (total + blancs) != suf:
            mismatches.append((code, total, blancs, suf, (total + blancs) - suf))

    if mismatches:
        # Print a readable report
        lines = ["Mismatch: expected suf_exprimes == sum(scores)+bull_blancs_nbr"]
        for code, total, blancs, suf, diff in mismatches[:30]:
            lines.append(f"  code={code}: sum(scores)={total}, blancs={blancs}, suf={suf}, diff={diff}")
        if len(mismatches) > 30:
            lines.append(f"  ... and {len(mismatches) - 30} more")
        raise ValidationError("\\n".join(lines))
