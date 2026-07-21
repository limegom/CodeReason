from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIAnalysis, AnalysisStatus, Assignment, HumanReview, Submission, SubmissionStatus


def mark_analyses_stale(
    session: Session,
    *,
    assignment_id: str | None = None,
    submission_id: str | None = None,
    reason: str = "Analysis inputs changed",
) -> int:
    if assignment_id is None and submission_id is None:
        raise ValueError("assignment_id or submission_id is required")

    statement = select(AIAnalysis).join(Submission)
    if assignment_id is not None:
        statement = statement.where(Submission.assignment_id == assignment_id)
    if submission_id is not None:
        statement = statement.where(AIAnalysis.submission_id == submission_id)

    analyses = list(session.scalars(statement).all())
    changed = 0
    for analysis in analyses:
        if analysis.status != AnalysisStatus.STALE:
            analysis.status = AnalysisStatus.STALE
            analysis.stale_reason = reason
            analysis.review_required = True
            reasons = list(analysis.review_reasons or [])
            if "STALE_INPUT" not in reasons:
                reasons.append("STALE_INPUT")
            analysis.review_reasons = reasons
            changed += 1
    return changed


def transition_submission_for_input_change(
    session: Session,
    submission: Submission,
    reason: str = "Analysis inputs changed",
) -> None:
    mark_analyses_stale(session, submission_id=submission.id, reason=reason)

    reviews = session.scalars(
        select(HumanReview).where(
            HumanReview.submission_id == submission.id,
            HumanReview.is_current.is_(True),
        )
    ).all()
    had_review_or_analysis = bool(reviews) or bool(submission.analyses)
    for review in reviews:
        review.is_current = False

    if submission.status == SubmissionStatus.APPROVED or had_review_or_analysis:
        submission.status = SubmissionStatus.REVIEW_REQUIRED


def invalidate_assignment_inputs(session: Session, assignment: Assignment, reason: str) -> int:
    assignment.analysis_input_version += 1
    submissions = session.scalars(
        select(Submission).where(Submission.assignment_id == assignment.id)
    ).all()
    for submission in submissions:
        transition_submission_for_input_change(session, submission, reason)
    return len(submissions)


def invalidate_submission_source(session: Session, submission: Submission, reason: str) -> None:
    submission.source_version += 1
    transition_submission_for_input_change(session, submission, reason)

