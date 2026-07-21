from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Assignment,
    HumanReview,
    ReviewStatus,
    RubricCriterion,
    RubricStatus,
    Submission,
    SubmissionStatus,
)


class FinalGradeUnavailable(Exception):
    """Raised when no current human-approved grade exists."""


class ReviewValidationError(Exception):
    pass


def rubric_is_grading_ready(rubric: RubricCriterion | Assignment) -> bool:
    """AI-structured criteria never become gradeable without human approval."""

    if isinstance(rubric, RubricCriterion):
        return rubric.active and rubric.approval_status == RubricStatus.HUMAN_APPROVED
    active = [criterion for criterion in rubric.rubric_criteria if criterion.active]
    return (
        bool(active)
        and all(
            criterion.approval_status == RubricStatus.HUMAN_APPROVED for criterion in active
        )
        and sum((criterion.max_score for criterion in active), start=Decimal("0"))
        == rubric.total_score
    )


def validate_human_scores(
    assignment: Assignment,
    score_by_criterion: dict[str, Decimal],
    *,
    require_complete: bool,
) -> None:
    criteria = {criterion.id: criterion for criterion in assignment.rubric_criteria if criterion.active}
    unknown = set(score_by_criterion) - set(criteria)
    if unknown:
        raise ReviewValidationError(f"Unknown or inactive rubric criteria: {sorted(unknown)}")
    if require_complete and set(score_by_criterion) != set(criteria):
        missing = set(criteria) - set(score_by_criterion)
        raise ReviewValidationError(f"Approved reviews require scores for every active criterion: {sorted(missing)}")
    for criterion_id, score in score_by_criterion.items():
        criterion = criteria[criterion_id]
        if score < 0 or score > criterion.max_score:
            raise ReviewValidationError(
                f"Score for {criterion.criterion_key} must be between 0 and {criterion.max_score}"
            )


def calculate_final_total(session: Session, submission_id: str) -> Decimal:
    """Return a grade only for a current, human-approved decision.

    Suggested AI scores are intentionally absent from this calculation.
    """

    submission = session.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.assignment), selectinload(Submission.human_reviews))
    )
    if submission is None:
        raise FinalGradeUnavailable("Submission does not exist")
    if submission.status != SubmissionStatus.APPROVED:
        raise FinalGradeUnavailable("Final total is unavailable until a human approves the current inputs")

    review = session.scalar(
        select(HumanReview)
        .where(
            HumanReview.submission_id == submission.id,
            HumanReview.status == ReviewStatus.APPROVED,
            HumanReview.is_current.is_(True),
            HumanReview.reviewed_assignment_version == submission.assignment.analysis_input_version,
            HumanReview.reviewed_source_version == submission.source_version,
        )
        .options(selectinload(HumanReview.scores))
        .order_by(HumanReview.approved_at.desc(), HumanReview.created_at.desc())
    )
    if review is None or review.approved_at is None:
        raise FinalGradeUnavailable("No human approval matches the current source, rubric, and tests")
    return sum((score.awarded_score for score in review.scores), start=Decimal("0"))


def approve_review(review: HumanReview, submission: Submission) -> None:
    review.status = ReviewStatus.APPROVED
    review.approved_at = datetime.now(timezone.utc)
    review.reviewed_assignment_version = submission.assignment.analysis_input_version
    review.reviewed_source_version = submission.source_version
    review.is_current = True
    submission.status = SubmissionStatus.APPROVED
