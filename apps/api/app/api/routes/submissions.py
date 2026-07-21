from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import PurePath

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, with_loader_criteria

from app.api.dependencies import require_entity, require_internal_write
from app.db import get_db
from app.errors import ApiError
from app.models import (
    AIAnalysis,
    AnalysisStatus,
    Assignment,
    DataProvenance,
    Evidence,
    EvidenceVisibility,
    ExecutionRun,
    ExecutionStatus,
    HumanReview,
    HumanRubricScore,
    ReviewStatus,
    RubricScore,
    SourceFile,
    Submission,
    SubmissionStatus,
    TestCase,
    TestResult,
)
from app.schemas.domain import (
    AIAnalysisRead,
    AnalyzeRequest,
    DeleteResponse,
    EvidenceCreate,
    EvidenceRead,
    ExecutionRunCreate,
    ExecutionRunRead,
    ExecutionRunUpdate,
    ExecuteRequest,
    FinalGradeRead,
    HumanReviewCreate,
    HumanReviewRead,
    SourceFileCreate,
    SourceFileRead,
    SubmissionCreate,
    SubmissionRead,
    TestResultCreate,
    TestResultRead,
    AIAnalysisCreate,
)
from app.services.evidence_policy import evidence_for_student
from app.services.grading_policy import (
    FinalGradeUnavailable,
    ReviewValidationError,
    calculate_final_total,
    rubric_is_grading_ready,
    validate_human_scores,
)
from app.services.staleness import invalidate_submission_source
from app.services.review_priority import derive_review_requirements
from app.services.ai_orchestrator import enqueue_analysis


router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
def create_submission(payload: SubmissionCreate, session: Session = Depends(get_db)) -> Submission:
    require_entity(session, Assignment, payload.assignment_id, "Assignment")
    submission = Submission(**payload.model_dump())
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


@router.get("", response_model=list[SubmissionRead])
def list_submissions(
    assignment_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    session: Session = Depends(get_db),
) -> list[Submission]:
    statement = select(Submission).order_by(Submission.created_at.desc()).offset(offset).limit(limit)
    if assignment_id is not None:
        statement = statement.where(Submission.assignment_id == assignment_id)
    return list(session.scalars(statement))


@router.get("/{submission_id}", response_model=SubmissionRead)
def get_submission(submission_id: str, session: Session = Depends(get_db)) -> Submission:
    return require_entity(session, Submission, submission_id, "Submission")


@router.post(
    "/{submission_id}/execute",
    response_model=ExecutionRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def execute_submission(
    submission_id: str,
    payload: ExecuteRequest,
    session: Session = Depends(get_db),
) -> ExecutionRun:
    submission = session.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.assignment))
    )
    if submission is None:
        raise ApiError(404, "NOT_FOUND", "Submission was not found", {"id": submission_id})
    current_sources = session.scalars(
        select(SourceFile).where(
            SourceFile.submission_id == submission.id,
            SourceFile.is_current.is_(True),
        )
    ).all()
    if len(current_sources) != 1:
        raise ApiError(
            409,
            "SOURCE_NOT_EXECUTABLE",
            "Execution requires exactly one current Python source file",
        )
    active_test_count = len(
        session.scalars(
            select(TestCase.id).where(
                TestCase.assignment_id == submission.assignment_id,
                TestCase.active.is_(True),
            )
        ).all()
    )
    if active_test_count == 0:
        raise ApiError(409, "NO_ACTIVE_TESTS", "Execution requires at least one active test case")
    run = ExecutionRun(
        submission_id=submission.id,
        status=ExecutionStatus.PENDING,
        runner_version="server-owned-pending",
        assignment_input_version=submission.assignment.analysis_input_version,
        source_version=submission.source_version,
        provenance=DataProvenance.LIVE,
        run_metadata={
            "job_type": "EXECUTION",
            "requested_via": "API",
            "auto_analyze": payload.analyze_after_execution,
            "provenance": "PENDING",
        },
    )
    session.add(run)
    submission.status = SubmissionStatus.QUEUED
    session.commit()
    session.refresh(run)
    return run


@router.post(
    "/{submission_id}/analyze",
    response_model=AIAnalysisRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_submission(
    submission_id: str,
    payload: AnalyzeRequest,
    session: Session = Depends(get_db),
) -> AIAnalysis:
    submission = require_entity(session, Submission, submission_id, "Submission")
    try:
        return enqueue_analysis(
            session,
            submission,
            execution_run_id=payload.execution_run_id,
        )
    except ValueError as exc:
        raise ApiError(409, "ANALYSIS_NOT_READY", str(exc)) from exc


@router.delete("/{submission_id}", response_model=DeleteResponse)
def delete_submission(submission_id: str, session: Session = Depends(get_db)) -> DeleteResponse:
    submission = require_entity(session, Submission, submission_id, "Submission")
    session.delete(submission)
    session.commit()
    return DeleteResponse(id=submission_id)


@router.post(
    "/{submission_id}/source-files",
    response_model=SourceFileRead,
    status_code=status.HTTP_201_CREATED,
)
def add_source_file(
    submission_id: str,
    payload: SourceFileCreate,
    session: Session = Depends(get_db),
) -> SourceFile:
    submission = require_entity(session, Submission, submission_id, "Submission")
    filename = payload.filename.strip()
    if PurePath(filename).name != filename or not filename.lower().endswith(".py"):
        raise ApiError(
            422,
            "INVALID_SOURCE_FILE",
            "filename must be a basename ending in .py",
        )

    current_files = session.scalars(
        select(SourceFile).where(
            SourceFile.submission_id == submission.id,
            SourceFile.is_current.is_(True),
        )
    ).all()
    for source_file in current_files:
        source_file.is_current = False

    invalidate_submission_source(session, submission, "Student source code changed")
    source_file = SourceFile(
        submission_id=submission.id,
        filename=filename,
        content=payload.content,
        content_sha256=hashlib.sha256(payload.content.encode("utf-8")).hexdigest(),
        revision=submission.source_version,
        is_current=True,
    )
    session.add(source_file)
    session.commit()
    session.refresh(source_file)
    return source_file


@router.get("/{submission_id}/source-files", response_model=list[SourceFileRead])
def list_source_files(
    submission_id: str,
    current_only: bool = True,
    session: Session = Depends(get_db),
) -> list[SourceFile]:
    require_entity(session, Submission, submission_id, "Submission")
    statement = select(SourceFile).where(SourceFile.submission_id == submission_id)
    if current_only:
        statement = statement.where(SourceFile.is_current.is_(True))
    return list(session.scalars(statement.order_by(SourceFile.revision, SourceFile.filename)))


@router.post(
    "/{submission_id}/execution-runs",
    response_model=ExecutionRunRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_execution_run(
    submission_id: str,
    payload: ExecutionRunCreate,
    _: None = Depends(require_internal_write),
    session: Session = Depends(get_db),
) -> ExecutionRun:
    require_entity(session, Submission, submission_id, "Submission")
    execution_run = ExecutionRun(submission_id=submission_id, **payload.model_dump())
    session.add(execution_run)
    session.commit()
    session.refresh(execution_run)
    return execution_run


@router.get("/{submission_id}/execution-runs", response_model=list[ExecutionRunRead])
def list_execution_runs(
    submission_id: str, session: Session = Depends(get_db)
) -> list[ExecutionRun]:
    require_entity(session, Submission, submission_id, "Submission")
    return list(
        session.scalars(
            select(ExecutionRun)
            .where(ExecutionRun.submission_id == submission_id)
            .order_by(ExecutionRun.created_at.desc())
        )
    )


@router.get("/{submission_id}/execution-runs/{run_id}", response_model=ExecutionRunRead)
def get_execution_run(
    submission_id: str, run_id: str, session: Session = Depends(get_db)
) -> ExecutionRun:
    return _run_for_submission(session, submission_id, run_id)


@router.patch(
    "/{submission_id}/execution-runs/{run_id}",
    response_model=ExecutionRunRead,
    include_in_schema=False,
)
def update_execution_run(
    submission_id: str,
    run_id: str,
    payload: ExecutionRunUpdate,
    _: None = Depends(require_internal_write),
    session: Session = Depends(get_db),
) -> ExecutionRun:
    execution_run = _run_for_submission(session, submission_id, run_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(execution_run, key, value)
    session.commit()
    session.refresh(execution_run)
    return execution_run


def _run_for_submission(session: Session, submission_id: str, run_id: str) -> ExecutionRun:
    execution_run = require_entity(session, ExecutionRun, run_id, "Execution run")
    if execution_run.submission_id != submission_id:
        raise ApiError(404, "NOT_FOUND", "Execution run was not found for this submission")
    return execution_run


@router.post(
    "/{submission_id}/execution-runs/{run_id}/test-results",
    response_model=TestResultRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_test_result(
    submission_id: str,
    run_id: str,
    payload: TestResultCreate,
    _: None = Depends(require_internal_write),
    session: Session = Depends(get_db),
) -> TestResult:
    execution_run = _run_for_submission(session, submission_id, run_id)
    submission = require_entity(session, Submission, submission_id, "Submission")
    test_case = require_entity(session, TestCase, payload.test_case_id, "Test case")
    if test_case.assignment_id != submission.assignment_id:
        raise ApiError(422, "TEST_CASE_MISMATCH", "Test case belongs to another assignment")
    effective_mode = test_case.comparison_mode or submission.assignment.comparison_mode
    if payload.applied_comparison_mode != effective_mode:
        raise ApiError(
            422,
            "COMPARISON_POLICY_MISMATCH",
            "Recorded comparison policy must match the effective assignment/test policy",
            {"expected": effective_mode, "received": payload.applied_comparison_mode},
        )
    test_result = TestResult(execution_run_id=execution_run.id, **payload.model_dump())
    session.add(test_result)
    session.commit()
    session.refresh(test_result)
    return test_result


@router.get(
    "/{submission_id}/execution-runs/{run_id}/test-results",
    response_model=list[TestResultRead],
)
def list_test_results(
    submission_id: str, run_id: str, session: Session = Depends(get_db)
) -> list[TestResult]:
    _run_for_submission(session, submission_id, run_id)
    return list(
        session.scalars(
            select(TestResult)
            .where(TestResult.execution_run_id == run_id)
            .order_by(TestResult.created_at)
        )
    )


@router.post(
    "/{submission_id}/evidence",
    response_model=EvidenceRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_evidence(
    submission_id: str,
    payload: EvidenceCreate,
    _: None = Depends(require_internal_write),
    session: Session = Depends(get_db),
) -> Evidence:
    require_entity(session, Submission, submission_id, "Submission")
    if payload.execution_run_id:
        _run_for_submission(session, submission_id, payload.execution_run_id)
    if payload.source_file_id:
        source_file = require_entity(session, SourceFile, payload.source_file_id, "Source file")
        if source_file.submission_id != submission_id:
            raise ApiError(422, "SOURCE_FILE_MISMATCH", "Source file belongs to another submission")
    if payload.test_result_id:
        test_result = require_entity(session, TestResult, payload.test_result_id, "Test result")
        if test_result.execution_run.submission_id != submission_id:
            raise ApiError(422, "TEST_RESULT_MISMATCH", "Test result belongs to another submission")
        if payload.execution_run_id and test_result.execution_run_id != payload.execution_run_id:
            raise ApiError(422, "RUN_MISMATCH", "Test result and execution run do not match")
    evidence = Evidence(submission_id=submission_id, **payload.model_dump())
    session.add(evidence)
    session.commit()
    session.refresh(evidence)
    return evidence


@router.get("/{submission_id}/evidence", response_model=list[EvidenceRead])
def list_evidence(
    submission_id: str,
    visibility: EvidenceVisibility | None = None,
    session: Session = Depends(get_db),
) -> list[Evidence]:
    require_entity(session, Submission, submission_id, "Submission")
    if visibility == EvidenceVisibility.INTERNAL:
        raise ApiError(
            403,
            "INTERNAL_EVIDENCE_FORBIDDEN",
            "Internal evidence is not available through this endpoint",
        )
    statement = select(Evidence).where(
        Evidence.submission_id == submission_id,
        Evidence.visibility != EvidenceVisibility.INTERNAL,
    )
    if visibility is not None:
        statement = statement.where(Evidence.visibility == visibility)
    return list(session.scalars(statement.order_by(Evidence.created_at)))


@router.get("/{submission_id}/evidence/student")
def list_student_evidence(
    submission_id: str, session: Session = Depends(get_db)
) -> list[dict]:
    require_entity(session, Submission, submission_id, "Submission")
    evidence_items = session.scalars(
        select(Evidence)
        .where(
            Evidence.submission_id == submission_id,
            Evidence.visibility == EvidenceVisibility.STUDENT_VISIBLE,
        )
        .options(
            selectinload(Evidence.test_result).selectinload(TestResult.test_case),
        )
        .order_by(Evidence.created_at)
    ).all()
    return [item for evidence in evidence_items if (item := evidence_for_student(evidence)) is not None]


@router.get("/{submission_id}/analyses", response_model=list[AIAnalysisRead])
def list_analyses(
    submission_id: str, session: Session = Depends(get_db)
) -> list[AIAnalysis]:
    require_entity(session, Submission, submission_id, "Submission")
    return list(
        session.scalars(
            select(AIAnalysis)
            .where(AIAnalysis.submission_id == submission_id)
            .options(
                selectinload(AIAnalysis.rubric_scores).selectinload(RubricScore.primary_evidence),
                with_loader_criteria(
                    Evidence,
                    Evidence.visibility != EvidenceVisibility.INTERNAL,
                    include_aliases=True,
                ),
            )
            .order_by(AIAnalysis.created_at.desc())
        )
    )


@router.post(
    "/{submission_id}/analyses",
    response_model=AIAnalysisRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_derived_analysis(
    submission_id: str,
    payload: AIAnalysisCreate,
    _: None = Depends(require_internal_write),
    session: Session = Depends(get_db),
) -> AIAnalysis:
    """Persist derived analysis without promoting any AI output to Evidence."""

    submission = session.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.assignment).selectinload(Assignment.rubric_criteria))
    )
    if submission is None:
        raise ApiError(404, "NOT_FOUND", "Submission was not found", {"id": submission_id})
    if not rubric_is_grading_ready(submission.assignment):
        raise ApiError(
            409,
            "RUBRIC_NOT_APPROVED",
            "AI-structured rubric criteria must be HUMAN_APPROVED before grading",
        )

    execution_run = None
    if payload.execution_run_id:
        execution_run = _run_for_submission(session, submission_id, payload.execution_run_id)

    criteria = {
        criterion.id: criterion
        for criterion in submission.assignment.rubric_criteria
        if criterion.active
    }
    used_evidence: dict[str, Evidence] = {}
    missing_score_evidence = False
    score_models: list[RubricScore] = []
    seen_criteria: set[str] = set()
    for score_payload in payload.rubric_scores:
        if score_payload.rubric_criterion_id in seen_criteria:
            raise ApiError(422, "DUPLICATE_RUBRIC_SCORE", "Each rubric criterion may be suggested once")
        seen_criteria.add(score_payload.rubric_criterion_id)
        criterion = criteria.get(score_payload.rubric_criterion_id)
        if criterion is None:
            raise ApiError(422, "RUBRIC_MISMATCH", "Rubric criterion is inactive or belongs elsewhere")
        if score_payload.suggested_score > criterion.max_score:
            raise ApiError(
                422,
                "SCORE_EXCEEDS_MAXIMUM",
                f"Suggested score exceeds the maximum for {criterion.criterion_key}",
            )
        if not score_payload.evidence_ids:
            missing_score_evidence = True

        evidence_items: list[Evidence] = []
        for evidence_id in score_payload.evidence_ids:
            evidence = used_evidence.get(evidence_id) or require_entity(
                session, Evidence, evidence_id, "Primary evidence"
            )
            if evidence.submission_id != submission.id:
                raise ApiError(422, "EVIDENCE_MISMATCH", "Evidence belongs to another submission")
            used_evidence[evidence_id] = evidence
            evidence_items.append(evidence)
        score = RubricScore(
            rubric_criterion_id=criterion.id,
            suggested_score=score_payload.suggested_score,
            interpretation=score_payload.interpretation,
            feedback=score_payload.feedback,
            model_reported_confidence=score_payload.model_reported_confidence,
        )
        score.primary_evidence = evidence_items
        score_models.append(score)

    execution_available = execution_run is not None and execution_run.status.value != "UNAVAILABLE"
    review_required, review_reasons = derive_review_requirements(
        evidence_count=0 if missing_score_evidence else len(used_evidence),
        conflicting_evidence=payload.conflicting_evidence,
        execution_available=execution_available,
        model_reported_confidence=payload.model_reported_confidence,
    )
    analysis = AIAnalysis(
        submission_id=submission.id,
        execution_run_id=payload.execution_run_id,
        status=payload.status,
        provider=payload.provider,
        provider_response_id=payload.provider_response_id,
        model_name=payload.model_name,
        prompt_version=payload.prompt_version,
        summary=payload.summary,
        feedback=payload.feedback,
        model_reported_confidence=payload.model_reported_confidence,
        review_required=review_required,
        review_reasons=[reason.value for reason in review_reasons],
        input_fingerprint=payload.input_fingerprint,
        assignment_input_version=submission.assignment.analysis_input_version,
        source_version=submission.source_version,
        sanitized_input_hash=payload.sanitized_input_hash,
        external_data_manifest=payload.external_data_manifest,
        token_usage=payload.token_usage,
        completed_at=datetime.now(timezone.utc) if payload.status == AnalysisStatus.COMPLETED else None,
    )
    analysis.rubric_scores = score_models
    session.add(analysis)
    submission.status = SubmissionStatus.REVIEW_REQUIRED
    session.commit()
    return session.scalar(
        select(AIAnalysis)
        .where(AIAnalysis.id == analysis.id)
        .options(
            selectinload(AIAnalysis.rubric_scores).selectinload(RubricScore.primary_evidence)
        )
    )


@router.post(
    "/{submission_id}/human-reviews",
    response_model=HumanReviewRead,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{submission_id}/review",
    response_model=HumanReviewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_human_review(
    submission_id: str,
    payload: HumanReviewCreate,
    session: Session = Depends(get_db),
) -> HumanReview:
    submission = session.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(
            selectinload(Submission.assignment).selectinload(Assignment.rubric_criteria),
            selectinload(Submission.human_reviews),
        )
    )
    if submission is None:
        raise ApiError(404, "NOT_FOUND", "Submission was not found", {"id": submission_id})

    ai_analysis = None
    if payload.ai_analysis_id:
        ai_analysis = require_entity(session, AIAnalysis, payload.ai_analysis_id, "AI analysis")
        if ai_analysis.submission_id != submission.id:
            raise ApiError(422, "ANALYSIS_MISMATCH", "AI analysis belongs to another submission")

    approving = payload.status == ReviewStatus.APPROVED
    if approving and not rubric_is_grading_ready(submission.assignment):
        raise ApiError(
            409,
            "RUBRIC_NOT_APPROVED",
            "Every active rubric criterion must be HUMAN_APPROVED before final grading",
        )
    if approving and ai_analysis is not None and ai_analysis.status == AnalysisStatus.STALE:
        raise ApiError(409, "STALE_ANALYSIS", "A stale AI analysis cannot support a current approval")

    score_by_criterion = {
        score.rubric_criterion_id: score.awarded_score for score in payload.scores
    }
    if len(score_by_criterion) != len(payload.scores):
        raise ApiError(422, "DUPLICATE_RUBRIC_SCORE", "Each rubric criterion may be scored once")
    try:
        validate_human_scores(
            submission.assignment,
            score_by_criterion,
            require_complete=approving,
        )
    except ReviewValidationError as exc:
        raise ApiError(422, "INVALID_HUMAN_SCORE", str(exc)) from exc

    for old_review in submission.human_reviews:
        if old_review.is_current:
            old_review.is_current = False

    review = HumanReview(
        submission_id=submission.id,
        ai_analysis_id=payload.ai_analysis_id,
        reviewer=payload.reviewer,
        status=payload.status,
        decision_reason=payload.decision_reason,
        reviewed_assignment_version=submission.assignment.analysis_input_version,
        reviewed_source_version=submission.source_version,
        is_current=True,
        approved_at=datetime.now(timezone.utc) if approving else None,
    )
    review.scores = [
        HumanRubricScore(
            rubric_criterion_id=score.rubric_criterion_id,
            awarded_score=score.awarded_score,
            reason=score.reason,
        )
        for score in payload.scores
    ]
    session.add(review)
    submission.status = SubmissionStatus.APPROVED if approving else SubmissionStatus.REVIEW_REQUIRED
    session.commit()
    session.refresh(review)
    return review


@router.get("/{submission_id}/human-reviews", response_model=list[HumanReviewRead])
def list_human_reviews(
    submission_id: str, session: Session = Depends(get_db)
) -> list[HumanReview]:
    require_entity(session, Submission, submission_id, "Submission")
    return list(
        session.scalars(
            select(HumanReview)
            .where(HumanReview.submission_id == submission_id)
            .options(selectinload(HumanReview.scores))
            .order_by(HumanReview.created_at.desc())
        )
    )


@router.get("/{submission_id}/final-grade", response_model=FinalGradeRead)
def get_final_grade(
    submission_id: str, session: Session = Depends(get_db)
) -> FinalGradeRead:
    try:
        final_total = calculate_final_total(session, submission_id)
    except FinalGradeUnavailable as exc:
        raise ApiError(409, "FINAL_GRADE_UNAVAILABLE", str(exc)) from exc
    review = session.scalar(
        select(HumanReview)
        .where(
            HumanReview.submission_id == submission_id,
            HumanReview.status == ReviewStatus.APPROVED,
            HumanReview.is_current.is_(True),
        )
        .order_by(HumanReview.approved_at.desc())
    )
    if review is None or review.approved_at is None:
        raise ApiError(409, "FINAL_GRADE_UNAVAILABLE", "No current human approval exists")
    return FinalGradeRead(
        submission_id=submission_id,
        human_review_id=review.id,
        final_total=Decimal(final_total),
        approved_at=review.approved_at,
    )
