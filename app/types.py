"""Verification outcome and batch types."""

from dataclasses import dataclass, field
from pathlib import Path

from app.models import DocumentModel
from app.rules.base import EvaluationResult


@dataclass
class VerificationOutcome:
    path: Path
    doc: DocumentModel
    evaluation: EvaluationResult
    link_statuses: dict[str, tuple[int | None, str]] = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return self.doc.filename

    @property
    def roll_number(self) -> str:
        return self.doc.metadata_derived.get("Roll Number", "")

    @property
    def name(self) -> str:
        return self.doc.metadata_derived.get("Name", "") or self.doc.header_name

    @property
    def email(self) -> str:
        return self.doc.metadata_derived.get("Email", "")
