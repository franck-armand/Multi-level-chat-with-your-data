from pathlib import Path
import csv
import tempfile

from edan.extract_docx import extract_docx_to_csv
from edan.validate import run_validations


def test_end_to_end_extract_and_validate():
    # Optional test: drop the DOCX into tests/fixtures/ to enable.
    docx = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "EDAN_2025_RESULTAT_NATIONAL_DETAILS.docx"
    if not docx.exists():
        return

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "edan.csv"
        extract_docx_to_csv(docx, out, delimiter=";")
        run_validations(out, delimiter=";")

        with out.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
        assert len(rows) > 1000
