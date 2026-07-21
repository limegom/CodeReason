from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AIAnalysis,
    AnalysisStatus,
    Assignment,
    ComparisonMode,
    ExecutionMode,
    HumanReview,
    HumanRubricScore,
    ReviewStatus,
    RubricCriterion,
    RubricScore,
    RubricStatus,
    Submission,
    SubmissionStatus,
)
from app.services.grading_policy import (
    FinalGradeUnavailable,
    calculate_final_total,
)
from app.services.staleness import invalidate_assignment_inputs, invalidate_submission_source
from tests.factories import persist


def make_assignment(session: Session) -> Assignment:
    return persist(
        session,
        Assignment,
        title="Matrix construction",
        description="Build a matrix from the supplied values.",
        total_score=Decimal("10"),
        execution_mode=ExecutionMode.FUNCTION,
        entry_function="make_matrix",
        arguments_schema={"type": "object"},
        comparison_mode=ComparisonMode.JSON_VALUE,
    )


def make_criterion(
    session: Session,
    assignment: Assignment,
    *,
    max_score: Decimal,
) -> RubricCriterion:
    return persist(
        session,
        RubricCriterion,
        assignment_id=assignment.id,
        criterion_key=f"criterion-{str(max_score).replace('.', '-')}",
        title=f"Criterion worth {max_score}",
        description="Evaluate only evidence observable in code and deterministic results.",
        max_score=max_score,
        approval_status=RubricStatus.HUMAN_APPROVED,
    )


@pytest.mark.parametrize(
    ("change_reason", "scope"),
    [
        ("SOURCE_CODE_CHANGED", "submission"),
        ("RUBRIC_CHANGED", "assignment"),
        ("TEST_CASE_CHANGED", "assignment"),
    ],
)
def test_input_changes_stale_analysis_and_reopen_approved_submission_without_losing_audit(
    db_session: Session,
    change_reason: str,
    scope: str,
) -> None:
    assignment = make_assignment(db_session)
    submission = persist(
        db_session,
        Submission,
        assignment_id=assignment.id,
        status=SubmissionStatus.APPROVED,
    )
    analysis = persist(
        db_session,
        AIAnalysis,
        submission_id=submission.id,
        status=AnalysisStatus.COMPLETED,
        model_name="test-provider",
        prompt_version="test-v1",
        input_fingerprint="initial-inputs",
        assignment_input_version=assignment.analysis_input_version,
        source_version=submission.source_version,
    )
    review = persist(
        db_session,
        HumanReview,
        submission_id=submission.id,
        reviewer="ta@example.test",
        status=ReviewStatus.APPROVED,
        reviewed_assignment_version=assignment.analysis_input_version,
        reviewed_source_version=submission.source_version,
        is_current=True,
        approved_at=datetime.now(timezone.utc),
    )
    review_id = review.id

    if scope == "submission":
        previous_version = submission.source_version
        invalidate_submission_source(db_session, submission, reason=change_reason)
        assert submission.source_version == previous_version + 1
    else:
        previous_version = assignment.analysis_input_version
        invalidate_assignment_inputs(db_session, assignment, reason=change_reason)
        assert assignment.analysis_input_version == previous_version + 1
    db_session.commit()
    db_session.expire_all()

    stale_analysis = db_session.get(AIAnalysis, analysis.id)
    assert stale_analysis.status == AnalysisStatus.STALE
    assert stale_analysis.review_required is True
    assert "STALE_INPUT" in stale_analysis.review_reasons
    assert stale_analysis.stale_reason == change_reason
    assert db_session.get(Submission, submission.id).status == SubmissionStatus.REVIEW_REQUIRED

    preserved_review = db_session.get(HumanReview, review_id)
    assert preserved_review is not None
    assert preserved_review.status == ReviewStatus.APPROVED
    assert preserved_review.is_current is False
    review_count = db_session.scalar(
        select(func.count()).select_from(HumanReview).where(
            HumanReview.submission_id == submission.id
        )
    )
    assert review_count == 1


def test_final_total_is_unavailable_without_an_approved_human_review(
    db_session: Session,
) -> None:
    assignment = make_assignment(db_session)
    criterion = make_criterion(db_session, assignment, max_score=Decimal("10"))
    submission = persist(
        db_session,
        Submission,
        assignment_id=assignment.id,
        # Even an inconsistent APPROVED flag must not bypass the review gate.
        status=SubmissionStatus.APPROVED,
    )
    in_progress_review = persist(
        db_session,
        HumanReview,
        submission_id=submission.id,
        reviewer="ta@example.test",
        status=ReviewStatus.IN_REVIEW,
        reviewed_assignment_version=assignment.analysis_input_version,
        reviewed_source_version=submission.source_version,
        is_current=True,
    )
    persist(
        db_session,
        HumanRubricScore,
        human_review_id=in_progress_review.id,
        rubric_criterion_id=criterion.id,
        awarded_score=Decimal("8"),
    )
    db_session.commit()

    with pytest.raises(FinalGradeUnavailable):
        calculate_final_total(db_session, submission.id)


def test_final_total_is_calculated_only_from_approved_human_rubric_scores(
    db_session: Session,
) -> None:
    assignment = make_assignment(db_session)
    correctness = make_criterion(db_session, assignment, max_score=Decimal("6"))
    structure = make_criterion(db_session, assignment, max_score=Decimal("4"))
    submission = persist(
        db_session,
        Submission,
        assignment_id=assignment.id,
        status=SubmissionStatus.APPROVED,
    )
    analysis = persist(
        db_session,
        AIAnalysis,
        submission_id=submission.id,
        status=AnalysisStatus.COMPLETED,
        model_name="test-provider",
        prompt_version="test-v1",
        input_fingerprint="initial-inputs",
        assignment_input_version=assignment.analysis_input_version,
        source_version=submission.source_version,
        review_required=False,
    )
    persist(
        db_session,
        RubricScore,
        analysis_id=analysis.id,
        rubric_criterion_id=correctness.id,
        suggested_score=Decimal("6"),
        interpretation="Derived suggestion backed by primary evidence.",
    )
    persist(
        db_session,
        RubricScore,
        analysis_id=analysis.id,
        rubric_criterion_id=structure.id,
        suggested_score=Decimal("4"),
        interpretation="Derived suggestion backed by primary evidence.",
    )
    review = persist(
        db_session,
        HumanReview,
        submission_id=submission.id,
        ai_analysis_id=analysis.id,
        reviewer="ta@example.test",
        status=ReviewStatus.APPROVED,
        reviewed_assignment_version=assignment.analysis_input_version,
        reviewed_source_version=submission.source_version,
        is_current=True,
        approved_at=datetime.now(timezone.utc),
    )
    persist(
        db_session,
        HumanRubricScore,
        human_review_id=review.id,
        rubric_criterion_id=correctness.id,
        awarded_score=Decimal("4.5"),
    )
    persist(
        db_session,
        HumanRubricScore,
        human_review_id=review.id,
        rubric_criterion_id=structure.id,
        awarded_score=Decimal("3"),
    )
    db_session.commit()

    final_total = calculate_final_total(db_session, submission.id)

    assert Decimal(str(final_total)) == Decimal("7.5")
