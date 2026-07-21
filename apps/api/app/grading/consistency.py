from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True, slots=True)
class ConsistencyRecord:
    submission_id: str
    rubric_id: str
    rubric_max_score: float
    test_status_vector: tuple[str, ...]
    error_category: str
    ast_feature_summary: dict[str, bool]
    exception_type: str | None
    signature_status: str
    ai_suggested_score: float
    final_human_score: float | None
    model_reported_confidence: float
    approved: bool
    evidence_ids: tuple[str, ...] = ()
    explanation: str = ""

    @property
    def effective_score(self) -> float:
        return self.final_human_score if self.final_human_score is not None else self.ai_suggested_score

    def fingerprint_payload(self) -> dict[str, object]:
        return {
            "test_status_vector": self.test_status_vector,
            "error_category": self.error_category,
            "ast_feature_summary": dict(sorted(self.ast_feature_summary.items())),
            "exception_type": self.exception_type,
            "signature_status": self.signature_status,
        }

    def fingerprint(self) -> str:
        canonical = json.dumps(self.fingerprint_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PotentialConsistencyIssue:
    rubric_id: str
    severity: Severity
    submission_ids: tuple[str, ...]
    reason: str
    comparison_evidence: tuple[str, ...]
    recommended_action: str
    fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class ConsistencyThresholds:
    low_confidence: float = 0.70
    same_fingerprint_score_fraction: float = 0.20
    large_human_change_fraction: float = 0.30
    absolute_score_floor: float = 2.0


def _issue(
    record: ConsistencyRecord,
    *,
    severity: Severity,
    reason: str,
    evidence: tuple[str, ...],
    action: str,
) -> PotentialConsistencyIssue:
    return PotentialConsistencyIssue(
        rubric_id=record.rubric_id,
        severity=severity,
        submission_ids=(record.submission_id,),
        reason=f"Potential issue: {reason}",
        comparison_evidence=evidence,
        recommended_action=action,
        fingerprint=record.fingerprint(),
    )


def find_potential_issues(
    records: list[ConsistencyRecord],
    thresholds: ConsistencyThresholds = ConsistencyThresholds(),
) -> list[PotentialConsistencyIssue]:
    """Return review leads without asserting unfairness or changing scores."""

    issues: list[PotentialConsistencyIssue] = []
    for record in records:
        if record.effective_score < record.rubric_max_score and not record.evidence_ids:
            issues.append(
                _issue(
                    record,
                    severity=Severity.HIGH,
                    reason="a deduction appears to have no linked Primary Evidence.",
                    evidence=(),
                    action="Open the submission and either attach relevant evidence or revise the score.",
                )
            )
        if record.effective_score > record.rubric_max_score:
            issues.append(
                _issue(
                    record,
                    severity=Severity.HIGH,
                    reason="the recorded score exceeds the rubric maximum.",
                    evidence=record.evidence_ids,
                    action="Review the score bounds before export.",
                )
            )
        if record.approved and record.model_reported_confidence < thresholds.low_confidence:
            issues.append(
                _issue(
                    record,
                    severity=Severity.MEDIUM,
                    reason="an analysis with low model-reported confidence was approved.",
                    evidence=record.evidence_ids,
                    action="Recheck the Primary Evidence; confidence is only a review-priority signal.",
                )
            )
        if record.final_human_score is not None:
            delta = abs(record.final_human_score - record.ai_suggested_score)
            cutoff = max(
                thresholds.absolute_score_floor,
                record.rubric_max_score * thresholds.large_human_change_fraction,
            )
            if delta > cutoff:
                issues.append(
                    _issue(
                        record,
                        severity=Severity.LOW,
                        reason="the human-approved score differs substantially from the AI suggestion.",
                        evidence=record.evidence_ids,
                        action="Confirm that the reviewer reason explains the difference.",
                    )
                )

    grouped: dict[tuple[str, str], list[ConsistencyRecord]] = {}
    for record in records:
        grouped.setdefault((record.rubric_id, record.fingerprint()), []).append(record)

    for (rubric_id, fingerprint), group in grouped.items():
        if len(group) < 2:
            continue
        scores = [item.effective_score for item in group]
        rubric_max = max(item.rubric_max_score for item in group)
        cutoff = max(thresholds.absolute_score_floor, rubric_max * thresholds.same_fingerprint_score_fraction)
        if max(scores) - min(scores) > cutoff:
            issues.append(
                PotentialConsistencyIssue(
                    rubric_id=rubric_id,
                    severity=Severity.HIGH,
                    submission_ids=tuple(item.submission_id for item in group),
                    reason=(
                        "Potential issue: submissions with the same deterministic fingerprint "
                        "have materially different scores."
                    ),
                    comparison_evidence=tuple(
                        evidence for item in group for evidence in item.evidence_ids
                    ),
                    recommended_action="Compare the linked Primary Evidence and reviewer reasons.",
                    fingerprint=fingerprint,
                )
            )

    repeated_explanations: dict[tuple[str, str], list[ConsistencyRecord]] = {}
    for record in records:
        normalized = " ".join(record.explanation.lower().split())
        if normalized:
            repeated_explanations.setdefault((record.rubric_id, normalized), []).append(record)
    for (rubric_id, _), group in repeated_explanations.items():
        if len(group) < 2:
            continue
        if len({item.error_category for item in group}) < 2:
            continue
        if len({item.fingerprint() for item in group}) < 2:
            continue
        issues.append(
            PotentialConsistencyIssue(
                rubric_id=rubric_id,
                severity=Severity.MEDIUM,
                submission_ids=tuple(item.submission_id for item in group),
                reason=(
                    "Potential issue: the same explanation is repeated across "
                    "submissions with different deterministic observations."
                ),
                comparison_evidence=tuple(
                    evidence for item in group for evidence in item.evidence_ids
                ),
                recommended_action=(
                    "Compare each explanation with its linked Primary Evidence and personalize it."
                ),
                fingerprint=None,
            )
        )

    return issues
