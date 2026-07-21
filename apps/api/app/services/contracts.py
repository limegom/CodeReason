from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from app.models import Assignment, Evidence, SourceFile, Submission


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """Backend-owned execution contract consumed by a sandbox adapter.

    An adapter must select its image and command from trusted configuration. Source
    transfer is expected to use docker cp or a tar stream, never a host bind mount.
    """

    assignment: Assignment
    submission: Submission
    source_files: Sequence[SourceFile]


class ExecutionAdapter(Protocol):
    def execute(self, request: ExecutionRequest) -> str:
        """Queue or execute a run and return its durable execution-run id."""


@dataclass(frozen=True, slots=True)
class SanitizedAIInput:
    submission_id: str
    redacted_source: str
    rubric: list[dict[str, Any]]
    primary_evidence: Sequence[Evidence]
    external_data_manifest: dict[str, Any]


class DerivedAnalysisProvider(Protocol):
    def analyze(self, payload: SanitizedAIInput) -> dict[str, Any]:
        """Return derived analysis only; providers never create primary evidence."""

