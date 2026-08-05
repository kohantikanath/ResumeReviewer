"""R2xx document-level rules."""

from app.config import EMOJI_PATTERN
from app.models import DocumentModel
from app.rules.base import RuleResult, Severity


def check_document_rules(doc: DocumentModel) -> list[RuleResult]:
    results: list[RuleResult] = []

    results.append(
        RuleResult(
            rule_id="R201",
            severity=Severity.HARD,
            passed=doc.page_count == 1,
            reason="Resume must be exactly one page",
            evidence=f"pages={doc.page_count}",
        )
    )

    results.append(
        RuleResult(
            rule_id="R202",
            severity=Severity.HARD,
            passed=doc.image_count == 0,
            reason="Embedded images are not allowed",
            evidence=f"images={doc.image_count}",
        )
    )

    emoji_match = EMOJI_PATTERN.search(doc.full_text)
    results.append(
        RuleResult(
            rule_id="R203",
            severity=Severity.HARD,
            passed=emoji_match is None,
            reason="Emojis are not allowed",
            evidence=emoji_match.group(0) if emoji_match else "",
        )
    )

    return results
