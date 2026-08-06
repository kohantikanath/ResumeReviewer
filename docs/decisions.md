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

Case-insensitive. Partial names allowed from the **start**: `Kohantika` passes for `Kohantika Nath`; `Kohantikanath` passes (no space). **HARD fail** for truncations like `kohan` or `kohantikaN`. **SOFT fail** if only surname is shown (e.g. `Nath`). Each failure includes an explicit reason.

LinkedIn, GitHub, and LeetCode profile handles are **not** checked against the student name (R307, R504 disabled).

## Broken links (report)

Summary **Failed Rules (JSON)** column lists every failure as JSON:
`[{"rule_id":"R303","rule":"...","reason":"Found abc@gmail.com but required domain is @sst.scaler.com"}]`

Details sheet has **Rule ID**, **Rule**, **Reason** (one row per failure). Each broken URL is its own R502/R503 row citing the exact URL, line, section, and anchor text (e.g. GitHub vs Live on the same line).

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
- One report row per failed URL with exact URL, line, section, and anchor text
