from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, with_loader_criteria

from app.models import (
    AIAnalysis,
    AnalysisStatus,
    Assignment,
    ConsistencyIssue,
    Evidence,
    EvidenceVisibility,
    ExecutionRun,
    HumanReview,
    RubricScore,
    SourceFile,
    Submission,
    SubmissionStatus,
    TestResult,
)
from app.schemas.domain import FinalGradeRead
from app.services.grading_policy import FinalGradeUnavailable, calculate_final_total, rubric_is_grading_ready


def assignment_overviews(session: Session) -> list[dict[str, Any]]:
    assignments = list(
        session.scalars(
            select(Assignment)
            .options(
                selectinload(Assignment.submissions),
                selectinload(Assignment.rubric_criteria),
            )
            .order_by(Assignment.created_at.desc())
        )
    )
    results: list[dict[str, Any]] = []
    for assignment in assignments:
        submissions = assignment.submissions
        terminal = sum(
            submission.status
            in {
                SubmissionStatus.REVIEW_REQUIRED,
                SubmissionStatus.APPROVED,
                SubmissionStatus.FAILED,
            }
            for submission in submissions
        )
        issue_count = session.scalar(
            select(func.count(ConsistencyIssue.id)).where(
                ConsistencyIssue.assignment_id == assignment.id
            )
        ) or 0
        results.append(
            {
                **{column.name: getattr(assignment, column.name) for column in Assignment.__table__.columns},
                "submission_count": len(submissions),
                "pending_review_count": sum(
                    submission.status == SubmissionStatus.REVIEW_REQUIRED
                    for submission in submissions
                ),
                "approved_count": sum(
                    submission.status == SubmissionStatus.APPROVED for submission in submissions
                ),
                "consistency_issue_count": int(issue_count),
                "analyzed_percent": round(100 * terminal / len(submissions)) if submissions else 0,
                "rubric_ready": rubric_is_grading_ready(assignment),
            }
        )
    return results


def _json_object(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def submission_review_bundle(session: Session, submission_id: str) -> dict[str, Any] | None:
    submission = session.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(
            selectinload(Submission.assignment).selectinload(Assignment.rubric_criteria),
            selectinload(Submission.human_reviews).selectinload(HumanReview.scores),
        )
    )
    if submission is None:
        return None

    source = session.scalar(
        select(SourceFile)
        .where(
            SourceFile.submission_id == submission.id,
            SourceFile.is_current.is_(True),
        )
        .order_by(SourceFile.created_at.desc())
    )
    run = session.scalar(
        select(ExecutionRun)
        .where(ExecutionRun.submission_id == submission.id)
        .options(
            selectinload(ExecutionRun.test_results).selectinload(TestResult.test_case)
        )
        .order_by(ExecutionRun.created_at.desc())
        .limit(1)
    )
    evidence_statement = (
        select(Evidence)
        .where(
            Evidence.submission_id == submission.id,
            Evidence.visibility != EvidenceVisibility.INTERNAL,
        )
        .options(
            selectinload(Evidence.test_result).selectinload(TestResult.test_case),
        )
        .order_by(Evidence.created_at)
    )
    if run is not None:
        evidence_statement = evidence_statement.where(Evidence.execution_run_id == run.id)
    evidence = list(session.scalars(evidence_statement))
    analysis = session.scalar(
        select(AIAnalysis)
        .where(AIAnalysis.submission_id == submission.id)
        .options(
            selectinload(AIAnalysis.rubric_scores).selectinload(
                RubricScore.primary_evidence
            ),
            with_loader_criteria(
                Evidence,
                Evidence.visibility != EvidenceVisibility.INTERNAL,
                include_aliases=True,
            ),
        )
        .order_by(AIAnalysis.created_at.desc())
        .limit(1)
    )

    final_grade = None
    try:
        total = calculate_final_total(session, submission.id)
    except FinalGradeUnavailable:
        pass
    else:
        review = next(
            (
                item
                for item in submission.human_reviews
                if item.is_current and item.approved_at is not None
            ),
            None,
        )
        if review is not None:
            final_grade = FinalGradeRead(
                submission_id=submission.id,
                human_review_id=review.id,
                final_total=total,
                approved_at=review.approved_at,
            )

    analysis_summary = _json_object(analysis.summary) if analysis else None
    feedback_payload = _json_object(analysis.feedback) if analysis else None
    visible_ids = {
        item.id
        for item in evidence
        if item.visibility == EvidenceVisibility.STUDENT_VISIBLE
        and not (item.test_result and item.test_result.test_case.is_hidden)
    }
    student_feedback: list[dict[str, Any]] = []
    uncertainties: list[str] = []
    analysis_is_current = bool(
        analysis is not None
        and analysis.status == AnalysisStatus.COMPLETED
        and analysis.assignment_input_version
        == submission.assignment.analysis_input_version
        and analysis.source_version == submission.source_version
    )
    if feedback_payload is not None and analysis_is_current:
        candidate_feedback = feedback_payload.get("feedback_to_student", [])
        if isinstance(candidate_feedback, list):
            for item in candidate_feedback:
                if not isinstance(item, dict):
                    continue
                cited = item.get("evidence_ids", [])
                if isinstance(cited, list) and cited and set(cited).issubset(visible_ids):
                    student_feedback.append(item)
        candidate_uncertainties = feedback_payload.get("uncertainties", [])
        if isinstance(candidate_uncertainties, list):
            uncertainties = [str(item) for item in candidate_uncertainties]

    return {
        "submission": submission,
        "assignment": submission.assignment,
        "source_file": source,
        "rubric_criteria": list(submission.assignment.rubric_criteria),
        "execution_run": run,
        "test_results": [
            {
                **{
                    column.name: getattr(result, column.name)
                    for column in TestResult.__table__.columns
                },
                "test_name": result.test_case.name,
                "is_hidden": result.test_case.is_hidden,
                "input_payload": result.test_case.input_payload,
                "expected_output": result.test_case.expected_output,
                "stdout": result.result_metadata.get("captured_stdout"),
                "visibility": (
                    EvidenceVisibility.REVIEWER_ONLY
                    if result.test_case.is_hidden
                    else EvidenceVisibility.STUDENT_VISIBLE
                ),
            }
            for result in (run.test_results if run is not None else [])
        ],
        "evidence": evidence,
        "analysis": analysis,
        "human_reviews": sorted(
            submission.human_reviews,
            key=lambda item: item.created_at,
            reverse=True,
        ),
        "final_grade": final_grade,
        "analysis_summary": analysis_summary,
        "student_feedback": student_feedback,
        "uncertainties": uncertainties,
    }
