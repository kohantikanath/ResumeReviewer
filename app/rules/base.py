"""Rule engine types and orchestration."""

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Callable

from app.models import DocumentModel


class Severity(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class Verdict(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"


@dataclass
class RuleResult:
    rule_id: str
    severity: Severity
    passed: bool
    reason: str = ""
    evidence: str = ""


@dataclass
class EvaluationResult:
    verdict: Verdict
    results: list[RuleResult] = field(default_factory=list)
    hard_fail_count: int = 0
    soft_flag_count: int = 0

    def failed_rules(self) -> list[str]:
        return [r.rule_id for r in self.results if not r.passed]

    def digest(self) -> str:
        failed = [r for r in self.results if not r.passed]
        if not failed:
            return "All checks passed"
        return "; ".join(f"{r.rule_id}: {r.reason}" for r in failed[:3])


CheckerFn = Callable[..., list[RuleResult]]


def load_ruleset(path: Path | None = None) -> list[dict]:
    ruleset_path = path or Path("ruleset.json")
    with open(ruleset_path, encoding="utf-8") as f:
        data = json.load(f)
    return data["rules"]


def aggregate_verdict(results: list[RuleResult]) -> EvaluationResult:
    hard_fails = sum(1 for r in results if not r.passed and r.severity == Severity.HARD)
    soft_flags = sum(1 for r in results if not r.passed and r.severity == Severity.SOFT)
    any_hard_fail = any(not r.passed and r.severity == Severity.HARD for r in results)
    verdict = Verdict.REVIEW if any_hard_fail else Verdict.PASS
    return EvaluationResult(
        verdict=verdict,
        results=results,
        hard_fail_count=hard_fails,
        soft_flag_count=soft_flags,
    )


def run_all_rules(
    doc: DocumentModel,
    metadata_row: dict | None = None,
    link_results: list[RuleResult] | None = None,
    student_self_check: bool = False,
) -> EvaluationResult:
    from app.rules.document_rules import check_document_rules
    from app.rules.file_rules import check_file_rules
    from app.rules.header_rules import check_header_rules
    from app.rules.link_rules import check_static_link_rules
    from app.rules.section_rules import check_section_rules

    results: list[RuleResult] = []
    results.extend(
        check_file_rules(doc, metadata_row, student_self_check=student_self_check)
    )
    results.extend(check_document_rules(doc))
    results.extend(check_header_rules(doc))
    results.extend(check_section_rules(doc))
    results.extend(check_static_link_rules(doc))
    if link_results:
        results.extend(link_results)
    return aggregate_verdict(results)
