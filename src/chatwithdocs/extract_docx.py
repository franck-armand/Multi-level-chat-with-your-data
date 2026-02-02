from __future__ import annotations

import csv
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .normalize import clean_text, parse_int, parse_percent, parse_score_or_int

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass
class Candidate:
    party: str
    name: str
    score: int
    pct: float
    elected: bool


@dataclass
class Summary:
    region: str
    code: str
    name: str
    nb_bv: int
    inscrits: int
    votants: int
    taux_participation: float
    bull_nuls: int
    suf_exprimes: int
    bull_blancs_nbr: int
    bull_blancs_percent: float


def _parse_candidate_from_cells(cells: List[str]) -> Optional[Candidate]:
    # Candidate columns are expected in cells[11..15] for both summary rows and continuation rows
    if len(cells) < 15:
        return None

    party = clean_text(cells[11])
    candidate = clean_text(cells[12])
    score = parse_score_or_int(cells[13])
    pct = parse_percent(cells[14])
    elected = "ELU" in clean_text(cells[15]).upper() if len(cells) > 15 else False

    if not party or not candidate or score is None or pct is None:
        return None

    return Candidate(party=party, name=candidate, score=score, pct=pct, elected=bool(elected))


def _expected_candidate_sum(s: Summary) -> int:
    # CEI identity: SUF_EXPRIMES = SUM(scores) + BULL_BLANCS_NBR
    return int(s.suf_exprimes) - int(s.bull_blancs_nbr)


def _reconcile_blocks(blocks: List[tuple[Summary, List[Candidate]]]) -> None:
    """
    Fix page-break boundary issues by moving candidates between consecutive blocks
    until SUM(scores) matches (suf_exprimes - bull_blancs_nbr) as closely as possible.

    This is deterministic and preserves candidate ordering.
    """
    if len(blocks) < 2:
        return

    max_passes = 20  # more than enough for a handful of boundary issues
    for _ in range(max_passes):
        changed = False

        for i in range(len(blocks) - 1):
            s_a, c_a = blocks[i]["summary"], blocks[i]["cands"]
            s_b, c_b = blocks[i+1]["summary"], blocks[i+1]["cands"]

            target_a = _expected_candidate_sum(s_a)
            sum_a = sum(c.score for c in c_a)
            diff = sum_a - target_a  # >0 => too many votes in A, move to B; <0 => missing votes in A, pull from B

            # If A has overflow, move trailing candidates to the *front* of B (preserves order)
            while diff > 0 and c_a:
                moved = c_a.pop()     # last candidate in A
                c_b.insert(0, moved)  # becomes first candidate in B
                changed = True
                diff -= moved.score

            # If A has deficit, pull leading candidates from B into the *end* of A (preserves order)
            while diff < 0 and c_b:
                moved = c_b.pop(0)  # first candidate in B
                c_a.append(moved)   # becomes last candidate in A
                changed = True
                diff += moved.score

        if not changed:
            break


def _iter_table_rows(docx_path: Path) -> List[List[str]]:
    with zipfile.ZipFile(docx_path) as z:
        xml_bytes = z.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    trs = root.findall(".//w:tbl/w:tr", NS)

    out: List[List[str]] = []
    for tr in trs:
        row_cells: List[str] = []
        for tc in tr.findall("./w:tc", NS):
            texts: List[str] = []
            for t in tc.findall(".//w:t", NS):
                if t.text:
                    texts.append(t.text)
            row_cells.append(clean_text(" ".join(texts)))
        out.append(row_cells)
    return out


def extract_docx_to_csv(docx_path: Path, out_csv: Path, delimiter: str = ";") -> None:
    rows = _iter_table_rows(docx_path)

    header_tokens = {
        "REGI ON",
        "CIRCONSCRIPTION",
        "NB BV",
        "INSCRITS",
        "VOTANTS",
        "TAUX DE PART.",
        "BULL. NULS",
        "SUF. EXPRIMES",
        "BULL. BLANCS",
        "NOMBRE",
        "GROUPEMENTS / PARTIS POLITIQUES",
        "CANDIDATS / LISTES DE CANDIDATS",
        "SCORES",
        "RESULTATS DES SCRUTINS",
    }

    def is_header_row(cells: List[str]) -> bool:
        joined = " ".join([c for c in cells if c]).upper()
        return any(tok in joined for tok in header_tokens)
    
    def parse_summary_row(cells: List[str]) -> Optional[Summary]:
        # Drop obvious non-data rows
        if len(cells) < 15:
            return None
        if cells[0].upper() in {"TOTAL"}:
            return None
        if cells[0].upper().startswith("ELECTION"):
            return None

        code = clean_text(cells[1])
        if not (len(code) == 3 and code.isdigit()):
            return None

        region = clean_text(cells[0]) if cells[0] else ""
        name = clean_text(cells[2])

        nb_bv = parse_int(cells[3])
        inscrits = parse_int(cells[4])
        votants = parse_int(cells[5])
        taux = parse_percent(cells[6])
        bull_nuls = parse_int(cells[7])
        suf = parse_int(cells[8])
        blanc_nbr = parse_int(cells[9])
        blanc_pct = parse_percent(cells[10])

        if None in (nb_bv, inscrits, votants, taux, bull_nuls, suf, blanc_nbr, blanc_pct):
            return None

        return Summary(
            region=region,
            code=code,
            name=name,
            nb_bv=nb_bv,
            inscrits=inscrits,
            votants=votants,
            taux_participation=taux,
            bull_nuls=bull_nuls,
            suf_exprimes=suf,
            bull_blancs_nbr=blanc_nbr,
            bull_blancs_percent=blanc_pct,
        )
    
    # 1. Build blocks (summary + candidates) 
    blocks: list[dict] = []
    current_region = ""

    for cells in rows:
        if not any(cells):
            continue
        if is_header_row(cells):
            continue

        s = parse_summary_row(cells)
        if s is not None:
            if s.region:
                current_region = s.region
            else:
                s.region = current_region

            blocks.append({"summary": s, "cands": []})

            cand = _parse_candidate_from_cells(cells)
            if cand is not None:
                blocks[-1]["cands"].append(cand)
            continue

        # candidate-only continuation row
        if not blocks:
            continue

        cand = _parse_candidate_from_cells(cells)
        if cand is not None:
            blocks[-1]["cands"].append(cand)

    # 2. Reconcile page-break boundary mistakes (181/182 etc.) 
    _reconcile_blocks(blocks)

    # 3. Write final CSV 
    fieldnames = [
        "region",
        "circonscription_code",
        "circonscription_name",
        "nb_bv",
        "inscrits",
        "votants",
        "taux_participation",
        "bull_nuls",
        "suf_exprimes",
        "bull_blancs_nbr",
        "bull_blancs_percent",
        "party",
        "candidate",
        "score",
        "score_percent",
        "elected",
    ]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()

        for blk in blocks:
            summary = blk["summary"]
            for cand in blk["cands"]:
                        writer.writerow(
                            {
                                "region": summary.region,
                                "circonscription_code": summary.code,
                                "circonscription_name": summary.name,
                                "nb_bv": summary.nb_bv,
                                "inscrits": summary.inscrits,
                                "votants": summary.votants,
                                "taux_participation": summary.taux_participation,
                                "bull_nuls": summary.bull_nuls,
                                "suf_exprimes": summary.suf_exprimes,
                                "bull_blancs_nbr": summary.bull_blancs_nbr,
                                "bull_blancs_percent": summary.bull_blancs_percent,
                                "party": cand.party,
                                "candidate": cand.name,
                                "score": cand.score,
                                "score_percent": cand.pct,
                                "elected": cand.elected,
                            }
                        )

