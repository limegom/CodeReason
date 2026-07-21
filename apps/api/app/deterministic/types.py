"""Value objects for directly observed grading evidence.

AST shape records syntax; it does not establish intent or understanding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EvidenceVisibility(StrEnum):
    INTERNAL = "INTERNAL"
    REVIEWER_ONLY = "REVIEWER_ONLY"
    STUDENT_VISIBLE = "STUDENT_VISIBLE"


class FindingSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    SECURITY = "SECURITY"


@dataclass(frozen=True, slots=True)
class SourceCodeLocation:
    """A location in the immutable submitted source file."""

    file: str
    line_start: int
    line_end: int
    column_start: int | None = None
    column_end: int | None = None

    def __post_init__(self) -> None:
        if not self.file or "/" in self.file or "\\" in self.file:
            raise ValueError("file must be a basename")
        if self.line_start < 1 or self.line_end < self.line_start:
            raise ValueError("invalid source line range")
        if self.column_start is not None and self.column_start < 0:
            raise ValueError("column_start must be non-negative")
        if self.column_end is not None and self.column_end < 0:
            raise ValueError("column_end must be non-negative")

    @property
    def primary_evidence_type(self) -> str:
        return "SourceCodeLocation"


@dataclass(frozen=True, slots=True)
class ASTFinding:
    """An observation produced directly from Python's AST."""

    rule: str
    passed: bool | None
    message: str
    location: SourceCodeLocation | None = None
    details: dict[str, Any] = field(default_factory=dict)
    visibility: EvidenceVisibility = EvidenceVisibility.REVIEWER_ONLY

    @property
    def primary_evidence_type(self) -> str:
        return "ASTFinding"


@dataclass(frozen=True, slots=True)
class StaticFinding:
    """A conservative static observation that may require reviewer context."""

    rule: str
    message: str
    severity: FindingSeverity = FindingSeverity.INFO
    location: SourceCodeLocation | None = None
    details: dict[str, Any] = field(default_factory=dict)
    visibility: EvidenceVisibility = EvidenceVisibility.REVIEWER_ONLY

    @property
    def primary_evidence_type(self) -> str:
        return "StaticFinding"


@dataclass(frozen=True, slots=True)
class ExecutionError:
    """A sanitized execution error, without a host/container traceback."""

    category: str
    exception_type: str | None
    message: str
    location: SourceCodeLocation | None = None
    visibility: EvidenceVisibility = EvidenceVisibility.REVIEWER_ONLY

    @property
    def primary_evidence_type(self) -> str:
        return "ExecutionError"
