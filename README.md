# ResumeVerify

Automated placement resume verification against SST template rules.

## Quick start

```bash
pip install -e ".[dev]"
python scripts/generate_metadata.py   # derive metadata.xlsx from PDF fixtures
python -m pytest -v
```

## Google Forms CSV (Drive links)

If your sheet looks like the ThoughtSpot / placement form export:

| Timestamp | Email Address | Name | Contact Number | Scaler CGPA | BITS CGPA | Resume |
|-----------|---------------|------|----------------|-------------|-----------|--------|
| … | student@sst.scaler.com | Shubham | … | 8.5 | 8.0 | `https://drive.google.com/open?id=…` |

**Web UI:** Option A — upload the `.csv` export only. The app downloads each PDF from Drive, then verifies.

**CLI:**

```bash
python scripts/process_form_csv.py "SST x ThoughtSpot (Responses).csv" --output-dir ./output
python scripts/process_form_csv.py responses.csv --output-dir ./output --check-links
```

Drive files must be shared as **Anyone with the link** (viewer access).

## Run API + upload UI

```bash
python -m uvicorn app.api.main:app --reload --port 8000
```

Open http://localhost:8000 — upload PDFs (+ optional metadata sheet), poll progress, download `results.xlsx`.

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Upload UI |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/batch?check_links=true` | Upload PDFs + optional metadata |
| `GET` | `/api/jobs/{id}` | Job status + summary |
| `GET` | `/api/jobs/{id}/report` | Download Excel report |

## Workflow

1. Upload student PDFs (`Name_RollNumber_SST.pdf` in production)
2. Optional metadata sheet (`Roll Number`, `Name`, `Email`) — or auto-derive via `scripts/generate_metadata.py`
3. Rule engine → **PASS** or **REVIEW** with itemized rule IDs
4. Excel report: Summary · Details · Link log

## Docs

- [Implementation decisions](docs/decisions.md)
- [ruleset.json](ruleset.json)

## Calibration

Eight sample PDFs in `tests/fixtures/samples/` — 4 Good (PASS), 4 Bad (REVIEW). Run:

```bash
python -m pytest tests/test_calibration.py -v
```
