from __future__ import annotations

from decimal import Decimal
import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.grading.consistency import ConsistencyRecord, find_potential_issues
from app.grading.export import ExportRecord, build_csv_export
from app.models import (
    AIAnalysis,
    AnalysisStatus,
    Assignment,
    ConsistencyIssue,
    ConsistencyIssueSeverity,
    ExecutionRun,
    HumanReview,
    ReviewStatus,
    RubricScore,
    SourceFile,
    Submission,
)
from app.services.grading_policy import FinalGradeUnavailable, calculate_final_total
from app.services.read_models import submission_review_bundle


def _latest_run(session: Session, submission_id: str) -> ExecutionRun | None:
    return session.scalar(
        select(ExecutionRun)
        .where(ExecutionRun.submission_id == submission_id)
        .order_by(ExecutionRun.created_at.desc())
        .limit(1)
    )


def _latest_current_analysis(session: Session, submission: Submission) -> AIAnalysis | None:
    return session.scalar(
        select(AIAnalysis)
        .where(
            AIAnalysis.submission_id == submission.id,
            AIAnalysis.status == AnalysisStatus.COMPLETED,
            AIAnalysis.assignment_input_version == submission.assignment.analysis_input_version,
            AIAnalysis.source_version == submission.source_version,
        )
        .options(
            selectinload(AIAnalysis.rubric_scores).selectinload(RubricScore.primary_evidence)
        )
        .order_by(AIAnalysis.created_at.desc())
        .limit(1)
    )


def _current_review(session: Session, submission: Submission) -> HumanReview | None:
    return session.scalar(
        select(HumanReview)
        .where(
            HumanReview.submission_id == submission.id,
            HumanReview.status == ReviewStatus.APPROVED,
            HumanReview.is_current.is_(True),
            HumanReview.reviewed_assignment_version
            == submission.assignment.analysis_input_version,
            HumanReview.reviewed_source_version == submission.source_version,
        )
        .options(selectinload(HumanReview.scores))
        .order_by(HumanReview.approved_at.desc())
        .limit(1)
    )


def _issue_fingerprint(*, rubric_id: str, observation_fingerprint: str) -> str:
    """Scope an observation fingerprint to one rubric criterion."""

    return hashlib.sha256(
        f"{rubric_id}:{observation_fingerprint}".encode("utf-8")
    ).hexdigest()


def _consistency_records(session: Session, assignment: Assignment) -> list[ConsistencyRecord]:
    records: list[ConsistencyRecord] = []
    for submission in assignment.submissions:
        analysis = _latest_current_analysis(session, submission)
        if analysis is None:
            continue
        run = _latest_run(session, submission.id)
        review = _current_review(session, submission)
        human_scores = (
            {score.rubric_criterion_id: float(score.awarded_score) for score in review.scores}
            if review
            else {}
        )
        metadata = run.run_metadata if run else {}
        ast_summary = {
            str(key): bool(value)
            for key, value in dict(metadata.get("ast_feature_summary") or {}).items()
            if value is not None
        }
        criterion_by_id = {criterion.id: criterion for criterion in assignment.rubric_criteria}
        for score in analysis.rubric_scores:
            criterion = criterion_by_id.get(score.rubric_criterion_id)
            if criterion is None:
                continue
            records.append(
                ConsistencyRecord(
                    submission_id=submission.id,
                    rubric_id=criterion.id,
                    rubric_max_score=float(criterion.max_score),
                    test_status_vector=tuple(
                        str(item) for item in metadata.get("test_status_vector", [])
                    ),
                    error_category=(
                        run.error_category.value if run and run.error_category else "NONE"
                    ),
                    ast_feature_summary=ast_summary,
                    exception_type=run.exception_type if run else None,
                    signature_status=run.signature_status if run and run.signature_status else "UNAVAILABLE",
                    ai_suggested_score=float(score.suggested_score),
                    final_human_score=human_scores.get(criterion.id),
                    model_reported_confidence=(
                        score.model_reported_confidence
                        if score.model_reported_confidence is not None
                        else analysis.model_reported_confidence or 0.0
                    ),
                    approved=review is not None,
                    evidence_ids=tuple(item.id for item in score.primary_evidence),
                    explanation=score.interpretation,
                )
            )
    return records


def run_consistency_check(session: Session, assignment: Assignment) -> list[ConsistencyIssue]:
    records = _consistency_records(session, assignment)
    generated = find_potential_issues(records)
    analysis_by_submission: dict[str, str | None] = {}
    for submission in assignment.submissions:
        analysis = _latest_current_analysis(session, submission)
        analysis_by_submission[submission.id] = analysis.id if analysis else None

    for item in generated:
        pairs = (
            [(item.submission_ids[0], compared) for compared in item.submission_ids[1:]]
            if len(item.submission_ids) > 1
            else [(item.submission_ids[0], None)]
        )
        issue_type = (
            "CONSISTENCY_FINGERPRINT"
            if len(item.submission_ids) > 1
            else "EVIDENCE_OR_SCORE_REVIEW"
        )
        for submission_id, compared_id in pairs:
            observation_fingerprint = item.fingerprint or hashlib.sha256(
                f"{issue_type}:{submission_id}:{compared_id}:{item.reason}".encode("utf-8")
            ).hexdigest()
            fingerprint = _issue_fingerprint(
                rubric_id=item.rubric_id,
                observation_fingerprint=observation_fingerprint,
            )
            existing = session.scalar(
                select(ConsistencyIssue).where(
                    ConsistencyIssue.assignment_id == assignment.id,
                    ConsistencyIssue.submission_id == submission_id,
                    ConsistencyIssue.compared_submission_id == compared_id,
                    ConsistencyIssue.issue_type == issue_type,
                    ConsistencyIssue.fingerprint_hash == fingerprint,
                )
            )
            if existing is not None:
                continue
            source_record = next(
                record for record in records if record.submission_id == submission_id
            )
            session.add(
                ConsistencyIssue(
                    assignment_id=assignment.id,
                    submission_id=submission_id,
                    compared_submission_id=compared_id,
                    analysis_id=analysis_by_submission.get(submission_id),
                    issue_type=issue_type,
                    severity=ConsistencyIssueSeverity(item.severity.value),
                    potential_issue=True,
                    description=item.reason,
                    fingerprint_hash=fingerprint,
                    test_status_vector=list(source_record.test_status_vector),
                    error_category=source_record.error_category,
                    ast_feature_summary=source_record.ast_feature_summary,
                    exception_type=source_record.exception_type,
                    signature_status=source_record.signature_status,
                )
            )
    session.commit()
    return list(
        session.scalars(
            select(ConsistencyIssue)
            .where(ConsistencyIssue.assignment_id == assignment.id)
            .order_by(ConsistencyIssue.created_at.desc())
        )
    )


def build_assignment_csv(session: Session, assignment: Assignment) -> str:
    records: list[ExportRecord] = []
    criterion_keys = {criterion.id: criterion.criterion_key for criterion in assignment.rubric_criteria}
    for submission in assignment.submissions:
        analysis = _latest_current_analysis(session, submission)
        review = _current_review(session, submission)
        run = _latest_run(session, submission.id)
        source = session.scalar(
            select(SourceFile)
            .where(
                SourceFile.submission_id == submission.id,
                SourceFile.is_current.is_(True),
            )
            .order_by(SourceFile.created_at.desc())
        )
        ai_scores = {
            score.rubric_criterion_id: float(score.suggested_score)
            for score in (analysis.rubric_scores if analysis else [])
        }
        human_scores = {
            score.rubric_criterion_id: float(score.awarded_score)
            for score in (review.scores if review else [])
        }
        approved = review is not None
        final_total: float | None = None
        if approved:
            try:
                final_total = float(calculate_final_total(session, submission.id))
            except FinalGradeUnavailable:
                approved = False
        bundle = submission_review_bundle(session, submission.id)
        feedback_items = bundle["student_feedback"] if bundle else []
        short_feedback = ""
        if feedback_items:
            first = feedback_items[0]
            short_feedback = str(first.get("next_step") or first.get("shows_evidence_of") or "")
        score_source = human_scores if approved else ai_scores
        records.append(
            ExportRecord(
                student_id=submission.student_reference,
                filename=source.filename if source else "",
                ai_suggested_total=(sum(ai_scores.values()) if analysis else None),
                human_approved=approved,
                final_total=final_total,
                rubric_scores={
                    criterion_keys[criterion_id]: score
                    for criterion_id, score in score_source.items()
                    if criterion_id in criterion_keys
                },
                error_category=(
                    run.error_category.value if run and run.error_category else "NONE"
                ),
                review_status=submission.status.value,
                short_feedback=short_feedback,
            )
        )
    return build_csv_export(records)
