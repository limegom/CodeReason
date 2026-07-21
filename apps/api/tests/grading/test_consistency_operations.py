from __future__ import annotations

from sqlalchemy.orm import Session

from app.grading.consistency import (
    ConsistencyRecord,
    PotentialConsistencyIssue,
    Severity,
)
from app.models import (
    Assignment,
    ConsistencyIssue,
    ConsistencyIssueSeverity,
    ConsistencyIssueStatus,
    ExecutionMode,
    Submission,
)
from app.services.grading_operations import (
    _issue_fingerprint,
    run_consistency_check,
)
from tests.factories import persist


def _record(submission_id: str) -> ConsistencyRecord:
    return ConsistencyRecord(
        submission_id=submission_id,
        rubric_id="correctness",
        rubric_max_score=10,
        test_status_vector=("PASSED",),
        error_category="NONE",
        ast_feature_summary={"syntax_valid": True},
        exception_type=None,
        signature_status="MATCHES",
        ai_suggested_score=4,
        final_human_score=None,
        model_reported_confidence=0.9,
        approved=False,
        evidence_ids=(),
    )


def test_persisted_issue_fingerprint_is_scoped_to_rubric() -> None:
    observation = "a" * 64

    assert _issue_fingerprint(
        rubric_id="correctness",
        observation_fingerprint=observation,
    ) != _issue_fingerprint(
        rubric_id="quality",
        observation_fingerprint=observation,
    )


def test_resolved_same_fingerprint_issue_is_not_reopened_as_a_duplicate(
    db_session: Session,
    monkeypatch,
) -> None:
    assignment = persist(
        db_session,
        Assignment,
        title="Consistency audit",
        execution_mode=ExecutionMode.STDIN_STDOUT,
    )
    submission = persist(
        db_session,
        Submission,
        assignment_id=assignment.id,
        student_reference="opaque-1",
    )
    observation = "b" * 64
    fingerprint = _issue_fingerprint(
        rubric_id="correctness",
        observation_fingerprint=observation,
    )
    persist(
        db_session,
        ConsistencyIssue,
        assignment_id=assignment.id,
        submission_id=submission.id,
        issue_type="EVIDENCE_OR_SCORE_REVIEW",
        severity=ConsistencyIssueSeverity.HIGH,
        status=ConsistencyIssueStatus.RESOLVED,
        potential_issue=True,
        description="Potential issue: already reviewed.",
        fingerprint_hash=fingerprint,
        test_status_vector=["PASSED"],
        ast_feature_summary={"syntax_valid": True},
    )
    record = _record(submission.id)
    generated = PotentialConsistencyIssue(
        rubric_id="correctness",
        severity=Severity.HIGH,
        submission_ids=(submission.id,),
        reason="Potential issue: a deduction has no evidence.",
        comparison_evidence=(),
        recommended_action="Review evidence.",
        fingerprint=observation,
    )
    monkeypatch.setattr(
        "app.services.grading_operations._consistency_records",
        lambda _session, _assignment: [record],
    )
    monkeypatch.setattr(
        "app.services.grading_operations.find_potential_issues",
        lambda _records: [generated],
    )

    issues = run_consistency_check(db_session, assignment)

    assert len(issues) == 1
    assert issues[0].status == ConsistencyIssueStatus.RESOLVED
