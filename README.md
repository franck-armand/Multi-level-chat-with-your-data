# EDAN 2025

A reproducible project to ingest an official CEI elections results PDF and (next) build a “chat with your data” experience on top of it.

**Source of truth**
- `EDAN_2025_RESULTAT_NATIONAL_DETAILS.pdf` (official)
- `EDAN_2025_RESULTAT_NATIONAL_DETAILS.docx` (a conversion of the PDF, manually provided to make extraction stable)

We parse the **DOCX tables** (WordprocessingML) because PDF text extraction introduced layout/rotation issues
and header bleed. The DOCX keeps the table structure, allowing a perfect export.

### 1. Setup (uv)

```bash
uv venv
# activate the venv (platform-specific)
# mac/linux:
source .venv/bin/activate
# windows (powershell):
# .venv\Scripts\Activate.ps1

uv pip install -e .
# (optional) dev tools
uv pip install -e ".[dev]"
```

### 2. Extract to CSV (semicolon-delimited)

```bash
edan extract --docx /path/to/EDAN_2025_RESULTAT_NATIONAL_DETAILS.docx --out data/edan_results.csv
```

The extractor writes `;`-delimited CSV to avoid ambiguity with commas in French numbers.

### 3. Validate (must pass before submission)

```bash
edan validate --csv data/edan_results.csv
```

### 4. Load into DuckDB (Level 1 readiness)

```bash
edan load-db --csv data/edan_results.csv --db data/edan.duckdb --table election_results

# If you prefer SQLite instead: (I implemented both for benchmark later on)
# edan load-db --engine sqlite --csv data/edan_results.csv --db data/edan.sqlite --table election_results
```

### 5. Example SQL sanity checks

```sql
-- distinct constituencies
SELECT COUNT(DISTINCT circonscription_code) FROM election_results;

-- vote identity check (must hold): suf_exprimes + bull_nuls = votants
SELECT circonscription_code
FROM election_results
GROUP BY circonscription_code
HAVING MAX(suf_exprimes) + MAX(bull_nuls) != MAX(votants);
```

### Project layout

- `src/edan/extract_docx.py`  DOCX -> records
- `src/edan/normalize.py`     cleaning/normalization (“formatting section”)
- `src/edan/validate.py`      validation suite
- `src/edan/db.py`            SQLite loader
- `src/edan/cli.py`           CLI entrypoint (`edan ...`)

### Reproducibility notes

- Deterministic parsing (no ML/OCR).
- CSV is semicolon-delimited.
- Numeric normalization removes spaces and thousands separators, and converts comma decimals to dot decimals.