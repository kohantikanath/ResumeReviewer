# ResumeVerify — Implementation Decisions

Decisions applied when the PRD left options open. Calibrated against 8 sample resumes.

## Verdict logic

| Condition | Verdict |
|-----------|---------|
| Zero HARD failures | **PASS** (SOFT flags may still appear in report) |
| Any HARD failure | **REVIEW** |

Management always makes the final decision; the tool never auto-rejects.

## R302 — Phone number

**Severity: SOFT** (not HARD).

Good 2 (Kumar Kartikay) passed manual review without a visible phone number. Missing phone → review note, not a definite violation.

## Metadata sheet

Columns (header row):

| Column | Required | Notes |
|--------|----------|-------|
| Roll Number | Yes | Match key; `23bcs10151` or numeric portal id (e.g. `10335`) |
| Name | Yes | Fuzzy match against PDF header (R104) |
| Email | No | Report column only; college email inferred from PDF |

If a PDF has no matching metadata row → **R103 HARD**.

## Filename convention (R103)

Accepted stem patterns (`.pdf` extension; optional ` - Display Name` suffix ignored):

| Pattern | Example |
|---------|---------|
| BCS roll + SST | `Pooja_Talele_23bcs10151_SST.pdf` |
| Numeric portal id + SST | `SwaimSahay_10335_SST.pdf` |
| With display suffix | `SwaimSahay_10335_SST - Swaim Sahay.pdf` |
| Name-only (Superset) | `Pooja_Talele.pdf` |

Roll/id in filename must match metadata `Roll Number` (`23bcs10151` or `10335`), or compact name matches metadata name.

## R104 — Name match

Case-insensitive. `Pooja Talele` vs `POOJA TALELE` passes. Uses normalized lowercase comparison plus fuzzy token match.

## Thresholds

| Check | Value |
|-------|-------|
| R104 name fuzzy match | Normalized lowercase; token_set_ratio ≥ 85 |
| Section font threshold | `span.size > modal_body_size × 1.15` |
| R101 min extractable chars | 200 |
| Phone regex | `(?:\+91[\s-]?)?[6-9]\d{9}` |
| Link timeout | 8s, 1 retry |
| Per-domain concurrency | 3 |

## Education (R403)

Both SST CGR and BITS CGPA required when both colleges appear (all template resumes list both).

- CGR labels: `CGR`, `Current CGR`, `SST CGR`
- CGPA labels: `CGPA`, `Current CGPA`
- Numeric: `\d+\.?\d*\s*/\s*10` or standalone decimal

## Link policy (R502 / R503)

- 404, DNS fail, connection refused → HARD (R502)
- 403, 429, 999, timeout on bot-block domains (LinkedIn, Tracxn, etc.) → SOFT (R503)
- Never hard-fail LinkedIn profile URLs on bot-block responses

## Link log (report)

**Link log** sheet lists only **failed** links (`hard_fail`, `soft`, `unknown`) — not URLs that returned OK. Each row includes URL, line/section/anchor text, status, and classification.
