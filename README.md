# ResumeVerify

Automated placement resume verification against SST template rules.

## Quick start

```bash
pip install -e ".[dev]"
python scripts/generate_metadata.py   # derive metadata.xlsx from PDF fixtures
pytest tests/test_calibration.py -v
```

## Workflow

1. Upload PDF resumes (filename: `Name_RollNumber_SST.pdf`)
2. Provide metadata sheet (`Roll Number`, `Name`, `Email`) — or derive from PDFs via `generate_metadata.py`
3. Run rule engine → **PASS** or **REVIEW** with itemized rule IDs

## Docs

- [PRD-aligned decisions](docs/decisions.md)
- [ruleset.json](ruleset.json)

## Calibration

Eight sample PDFs in `tests/fixtures/samples/` — 4 Good (PASS), 4 Bad (REVIEW).
