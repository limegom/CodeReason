from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.policy import (
    AnalysisPolicyContext,
    AnalysisPolicyError,
    RubricBound,
    validate_analysis,
    withhold_unsafe_student_feedback,
)
from app.ai.prompts import PROMPT_VERSION, RUBRIC_PROMPT_VERSION, build_grading_payload
from app.ai.provider import (
    AnalysisProvider,
    OpenAIAnalysisProvider,
    ProviderUnavailableError,
)
from app.ai.redaction import RedactionResult, redact_for_external_provider
from app.config import get_settings
from app.models import (
    AIAnalysis,
    AnalysisStatus,
    Assignment,
    DataProvenance,
    Evidence,
    EvidenceKind,
    EvidenceVisibility,
    ExecutionRun,
    ExecutionStatus,
    ReviewTrigger,
    RubricCriterion,
    RubricOrigin,
    RubricParseJob,
    RubricScore,
    RubricStatus,
    SourceFile,
    Submission,
    SubmissionStatus,
    TestResult,
)
from app.services.evidence_policy import evidence_for_external_ai
from app.services.grading_policy import rubric_is_grading_ready
from app.services.staleness import invalidate_assignment_inputs


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provider(provider: AnalysisProvider | None) -> AnalysisProvider:
    if provider is not None:
        return provider
    settings = get_settings()
    return OpenAIAnalysisProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )


def _redaction_manifest(
    result: RedactionResult,
    *,
    fields_sent: list[str],
) -> dict[str, Any]:
    return {
        "fields_sent": fields_sent,
        "redacted": result.redaction_count > 0,
        "redaction_count": result.redaction_count,
        "redaction_categories": [finding.category for finding in result.findings],
        "redaction_is_best_effort": True,
        "hidden_test_values_withheld": True,
        "model_tools_enabled": False,
    }


def enqueue_analysis(
    session: Session,
    submission: Submission,
    *,
    execution_run_id: str | None = None,
) -> AIAnalysis:
    """Create a server-owned analysis job without calling a provider in the API."""

    assignment = session.scalar(
        select(Assignment)
        .where(Assignment.id == submission.assignment_id)
        .options(selectinload(Assignment.rubric_criteria))
    )
    if assignment is None or not rubric_is_grading_ready(assignment):
        raise ValueError("Every active rubric criterion must be HUMAN_APPROVED before analysis")

    if execution_run_id is None:
        execution_run_id = session.scalar(
            select(ExecutionRun.id)
            .where(ExecutionRun.submission_id == submission.id)
            .order_by(ExecutionRun.created_at.desc())
            .limit(1)
        )
    if execution_run_id is not None:
        run = session.get(ExecutionRun, execution_run_id)
        if run is None or run.submission_id != submission.id:
            raise ValueError("Execution run does not belong to the submission")

    settings = get_settings()
    fingerprint = _sha256(
        f"{submission.id}:{assignment.analysis_input_version}:"
        f"{submission.source_version}:{execution_run_id or 'no-execution'}"
    )
    analysis = AIAnalysis(
        submission_id=submission.id,
        execution_run_id=execution_run_id,
        status=AnalysisStatus.PENDING,
        provider="openai",
        model_name=settings.openai_model,
        prompt_version=PROMPT_VERSION,
        review_required=True,
        review_reasons=[ReviewTrigger.MISSING_EVIDENCE.value],
        input_fingerprint=fingerprint,
        assignment_input_version=assignment.analysis_input_version,
        source_version=submission.source_version,
        external_data_manifest={
            "status": "NOT_SENT",
            "fields_sent": [],
            "redaction_is_best_effort": True,
        },
        provenance=DataProvenance.UNAVAILABLE,
    )
    session.add(analysis)
    submission.status = SubmissionStatus.QUEUED
    session.commit()
    session.refresh(analysis)
    return analysis


def enqueue_rubric_parse(
    session: Session,
    assignment: Assignment,
    *,
    policy_text: str,
) -> RubricParseJob:
    settings = get_settings()
    job = RubricParseJob(
        assignment_id=assignment.id,
        status=AnalysisStatus.PENDING,
        policy_text=policy_text,
        provider="openai",
        model_name=settings.openai_model,
        prompt_version=RUBRIC_PROMPT_VERSION,
        input_fingerprint=_sha256(
            f"{assignment.id}:{assignment.analysis_input_version}:{policy_text}"
        ),
        external_data_manifest={
            "status": "NOT_SENT",
            "fields_sent": [],
            "redaction_is_best_effort": True,
        },
        provenance=DataProvenance.UNAVAILABLE,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _claim_id(session: Session, model: type[Any]) -> str | None:
    cutoff = _utcnow() - timedelta(minutes=15)
    abandoned = session.scalars(
        select(model).where(
            model.status == AnalysisStatus.RUNNING,
            model.updated_at < cutoff,
        )
    ).all()
    for stale_job in abandoned:
        stale_job.status = AnalysisStatus.PENDING
        stale_job.external_data_manifest = {
            **dict(stale_job.external_data_manifest or {}),
            "reclaimed_after_abandoned_worker": True,
        }
    if abandoned:
        session.commit()
    statement = (
        select(model)
        .where(model.status == AnalysisStatus.PENDING)
        .order_by(model.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.scalar(statement)
    if job is None:
        return None
    job.status = AnalysisStatus.RUNNING
    session.commit()
    return str(job.id)


def _load_analysis(session: Session, analysis_id: str) -> AIAnalysis | None:
    return session.scalar(
        select(AIAnalysis)
        .where(AIAnalysis.id == analysis_id)
        .options(
            selectinload(AIAnalysis.submission)
            .selectinload(Submission.assignment)
            .selectinload(Assignment.rubric_criteria),
        )
    )


def _analysis_evidence(session: Session, analysis: AIAnalysis) -> list[Evidence]:
    statement = (
        select(Evidence)
        .where(Evidence.submission_id == analysis.submission_id)
        .options(
            selectinload(Evidence.test_result).selectinload(TestResult.test_case),
        )
        .order_by(Evidence.created_at)
    )
    if analysis.execution_run_id is not None:
        statement = statement.where(Evidence.execution_run_id == analysis.execution_run_id)
    return list(session.scalars(statement))


def _has_conflicting_evidence(
    evidence_items: list[Evidence],
    run: ExecutionRun | None,
) -> bool:
    """Derive conservative, observable conflict signals without model judgment."""

    test_statuses: set[str] = set()
    outcomes_by_rule: dict[str, set[bool]] = {}
    for evidence in evidence_items:
        details = evidence.details if isinstance(evidence.details, dict) else {}
        if details.get("conflicting_evidence") is True or details.get("conflict") is True:
            return True
        if evidence.kind == EvidenceKind.TEST_RESULT:
            status = details.get("status")
            if isinstance(status, str):
                test_statuses.add(status)
        rule = details.get("rule")
        passed = details.get("passed")
        if isinstance(rule, str) and isinstance(passed, bool):
            outcomes_by_rule.setdefault(rule, set()).add(passed)

    # Mixed deterministic outcomes are a conservative review signal. They
    # describe behavior that varies across observed cases without claiming why.
    if "PASSED" in test_statuses and any(status != "PASSED" for status in test_statuses):
        return True
    if any(len(outcomes) > 1 for outcomes in outcomes_by_rule.values()):
        return True

    if run is not None:
        features = run.run_metadata.get("ast_feature_summary", {})
        exists = features.get("expected_function_exists") if isinstance(features, dict) else None
        if exists is True and run.signature_status == "MISSING_FUNCTION":
            return True
        if exists is False and run.signature_status == "MATCHES":
            return True
    return False


def _execution_is_unavailable(run: ExecutionRun | None) -> bool:
    return bool(
        run is None
        or run.status == ExecutionStatus.UNAVAILABLE
        or run.run_metadata.get("execution_available") is False
    )


def _fail_analysis(
    session: Session,
    analysis: AIAnalysis,
    *,
    message: str,
    manifest: dict[str, Any] | None = None,
    review_reason: ReviewTrigger = ReviewTrigger.MISSING_EVIDENCE,
) -> None:
    analysis.status = AnalysisStatus.FAILED
    analysis.summary = message
    analysis.review_required = True
    reasons = {review_reason.value}
    run = (
        session.get(ExecutionRun, analysis.execution_run_id)
        if analysis.execution_run_id
        else None
    )
    if _execution_is_unavailable(run):
        reasons.add(ReviewTrigger.EXECUTION_UNAVAILABLE.value)
    analysis.review_reasons = sorted(reasons)
    analysis.provenance = DataProvenance.UNAVAILABLE
    analysis.completed_at = _utcnow()
    if manifest is not None:
        analysis.external_data_manifest = manifest
    analysis.submission.status = SubmissionStatus.REVIEW_REQUIRED
    session.commit()


def process_analysis_job(
    session: Session,
    analysis_id: str,
    *,
    provider: AnalysisProvider | None = None,
) -> AIAnalysis:
    analysis = _load_analysis(session, analysis_id)
    if analysis is None:
        raise ValueError("Analysis job does not exist")
    submission = analysis.submission
    assignment = submission.assignment

    if (
        analysis.assignment_input_version != assignment.analysis_input_version
        or analysis.source_version != submission.source_version
    ):
        analysis.status = AnalysisStatus.STALE
        analysis.stale_reason = "Assignment, rubric, tests, or source changed before analysis ran"
        analysis.review_required = True
        analysis.review_reasons = [ReviewTrigger.STALE_INPUT.value]
        analysis.completed_at = _utcnow()
        submission.status = SubmissionStatus.REVIEW_REQUIRED
        session.commit()
        return analysis

    if not rubric_is_grading_ready(assignment):
        _fail_analysis(
            session,
            analysis,
            message="Analysis unavailable because the rubric is not HUMAN_APPROVED.",
        )
        return analysis

    source = session.scalar(
        select(SourceFile)
        .where(
            SourceFile.submission_id == submission.id,
            SourceFile.is_current.is_(True),
        )
        .order_by(SourceFile.created_at.desc())
    )
    if source is None:
        _fail_analysis(session, analysis, message="Analysis unavailable because source is missing.")
        return analysis

    evidence_items = _analysis_evidence(session, analysis)
    projected: list[dict[str, Any]] = []
    projected_models: dict[str, Evidence] = {}
    for evidence in evidence_items:
        item = evidence_for_external_ai(evidence)
        if item is not None:
            projected.append(item)
            projected_models[evidence.id] = evidence

    student_visible_ids = sorted(
        evidence.id
        for evidence in evidence_items
        if evidence.id in projected_models
        and evidence.visibility == EvidenceVisibility.STUDENT_VISIBLE
        and not (evidence.test_result and evidence.test_result.test_case.is_hidden)
    )

    approved = [
        criterion
        for criterion in assignment.rubric_criteria
        if criterion.active and criterion.approval_status == RubricStatus.HUMAN_APPROVED
    ]
    rubric_payload = [
        {
            "id": criterion.id,
            "criterion_key": criterion.criterion_key,
            "title": criterion.title,
            "description": criterion.description,
            "max_score": float(criterion.max_score),
            "rules": criterion.rules,
            "approval_status": criterion.approval_status.value,
        }
        for criterion in approved
    ]
    raw_payload = build_grading_payload(
        assignment_description=assignment.description,
        approved_rubric=rubric_payload,
        redacted_source_code=source.content,
        primary_evidence=projected,
        student_feedback_allowed_evidence_ids=student_visible_ids,
        maximum_total=float(assignment.total_score),
    )
    redaction = redact_for_external_provider(
        raw_payload,
        explicit_identifiers=(submission.student_reference,),
    )
    fields_sent = [
        "assignment_description",
        "human_approved_rubric",
        "redacted_source_code",
        "sanitized_primary_evidence",
        "student_feedback_allowed_evidence_ids",
        "score_bounds",
    ]
    manifest = _redaction_manifest(redaction, fields_sent=fields_sent)
    manifest["status"] = "PREPARED_NOT_SENT"
    analysis.sanitized_input_hash = _sha256(redaction.redacted_text)
    analysis.external_data_manifest = manifest

    try:
        selected_provider = _provider(provider)
    except ProviderUnavailableError as exc:
        manifest["status"] = "NOT_SENT_PROVIDER_UNAVAILABLE"
        _fail_analysis(
            session,
            analysis,
            message=f"Analysis unavailable: {type(exc).__name__}.",
            manifest=manifest,
            review_reason=ReviewTrigger.PROVIDER_UNAVAILABLE,
        )
        return analysis

    manifest["status"] = "TRANSMISSION_ATTEMPTED"
    analysis.external_data_manifest = dict(manifest)
    # Persist the attempt marker before network I/O. If the worker terminates
    # during the call, a later reclaim must not claim that nothing was sent.
    session.commit()
    try:
        result = asyncio.run(selected_provider.analyze(redaction.redacted_text))
    except (ProviderUnavailableError, ValueError, TypeError, AttributeError) as exc:
        manifest["status"] = "TRANSMISSION_FAILED"
        manifest["may_have_been_transmitted"] = True
        _fail_analysis(
            session,
            analysis,
            message=f"Analysis unavailable: {type(exc).__name__}.",
            manifest=manifest,
            review_reason=ReviewTrigger.PROVIDER_UNAVAILABLE,
        )
        return analysis

    manifest["status"] = "SENT"
    analysis.external_data_manifest = dict(manifest)
    analysis.provider = result.provider
    analysis.provider_response_id = result.response_id
    analysis.model_name = result.resolved_model
    analysis.token_usage = result.usage
    feedback_withheld = False
    try:
        run = session.get(ExecutionRun, analysis.execution_run_id) if analysis.execution_run_id else None
        evidence_kinds = {
            evidence_id: evidence.kind.value for evidence_id, evidence in projected_models.items()
        }
        student_visible = frozenset(student_visible_ids)
        conflicting_evidence = _has_conflicting_evidence(evidence_items, run)
        policy_context = AnalysisPolicyContext(
            rubrics=tuple(
                RubricBound(
                    criterion.id,
                    float(criterion.max_score),
                    human_approved=True,
                    evaluation_type=str(criterion.rules.get("evaluation_type", "hybrid")),
                )
                for criterion in approved
            ),
            available_evidence_ids=frozenset(projected_models),
            evidence_kinds=evidence_kinds,
            student_visible_evidence_ids=student_visible,
            conflicting_evidence=conflicting_evidence,
            execution_unavailable=_execution_is_unavailable(run),
        )
        feedback_withheld = withhold_unsafe_student_feedback(
            result.parsed,  # type: ignore[arg-type]
            policy_context,
        )
        output = validate_analysis(result.parsed, policy_context)  # type: ignore[arg-type]
    except (
        AnalysisPolicyError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        _fail_analysis(
            session,
            analysis,
            message=f"Analysis unavailable: {type(exc).__name__}.",
            manifest=manifest,
        )
        return analysis

    analysis.rubric_scores.clear()
    confidences: list[float] = []
    missing_evidence = False
    manual_review = bool(output.uncertainties)
    for item in output.rubric_results:
        evidence = [projected_models[evidence_id] for evidence_id in item.evidence_ids]
        missing_evidence = missing_evidence or not evidence
        manual_review = manual_review or item.manual_review_required
        confidences.append(item.model_reported_confidence)
        score = RubricScore(
            rubric_criterion_id=item.rubric_id,
            suggested_score=Decimal(str(item.suggested_score)),
            interpretation=item.reason,
            feedback=None,
            model_reported_confidence=item.model_reported_confidence,
        )
        score.primary_evidence = evidence
        analysis.rubric_scores.append(score)

    overall_confidence = min(confidences) if confidences else None
    reasons: list[str] = []
    if missing_evidence or feedback_withheld:
        reasons.append(ReviewTrigger.MISSING_EVIDENCE.value)
    if overall_confidence is None or overall_confidence < 0.70:
        reasons.append(ReviewTrigger.LOW_MODEL_REPORTED_CONFIDENCE.value)
    run = session.get(ExecutionRun, analysis.execution_run_id) if analysis.execution_run_id else None
    if _execution_is_unavailable(run):
        reasons.append(ReviewTrigger.EXECUTION_UNAVAILABLE.value)
    if conflicting_evidence:
        reasons.append(ReviewTrigger.CONFLICTING_EVIDENCE.value)
    analysis.provider = result.provider
    analysis.provider_response_id = result.response_id
    analysis.model_name = result.resolved_model
    analysis.summary = json.dumps(
        output.submission_summary.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    analysis.feedback = json.dumps(
        {
            "feedback_to_student": [
                item.model_dump(mode="json") for item in output.feedback_to_student
            ],
            "uncertainties": output.uncertainties,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    analysis.model_reported_confidence = overall_confidence
    analysis.review_required = manual_review or bool(reasons)
    analysis.review_reasons = sorted(set(reasons))
    analysis.token_usage = result.usage
    analysis.status = AnalysisStatus.COMPLETED
    analysis.provenance = DataProvenance.LIVE
    analysis.completed_at = _utcnow()
    submission.status = SubmissionStatus.REVIEW_REQUIRED
    session.commit()
    return analysis


def _criterion_key(raw: str, *, index: int, job_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw.strip()).strip("-.").lower()
    if not slug:
        slug = f"criterion-{index}"
    suffix = job_id.replace("-", "")[:8]
    return f"{slug[:68]}-{suffix}"[:80]


def process_rubric_parse_job(
    session: Session,
    job_id: str,
    *,
    provider: AnalysisProvider | None = None,
) -> RubricParseJob:
    job = session.scalar(
        select(RubricParseJob)
        .where(RubricParseJob.id == job_id)
        .options(selectinload(RubricParseJob.assignment))
    )
    if job is None:
        raise ValueError("Rubric parse job does not exist")

    raw_payload = json.dumps(
        {
            "natural_language_rubric_policy": job.policy_text,
            "assignment_total_score": float(job.assignment.total_score),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    redaction = redact_for_external_provider(raw_payload)
    manifest = _redaction_manifest(
        redaction,
        fields_sent=["natural_language_rubric_policy", "assignment_score_bounds"],
    )
    manifest["status"] = "PREPARED_NOT_SENT"
    job.sanitized_input_hash = _sha256(redaction.redacted_text)
    job.external_data_manifest = manifest
    try:
        selected_provider = _provider(provider)
    except ProviderUnavailableError as exc:
        manifest["status"] = "NOT_SENT_PROVIDER_UNAVAILABLE"
        job.external_data_manifest = manifest
        job.status = AnalysisStatus.FAILED
        job.error_message = f"Rubric parsing unavailable: {type(exc).__name__}."
        job.provenance = DataProvenance.UNAVAILABLE
        job.completed_at = _utcnow()
        session.commit()
        return job

    manifest["status"] = "TRANSMISSION_ATTEMPTED"
    job.external_data_manifest = dict(manifest)
    session.commit()
    try:
        result = asyncio.run(selected_provider.parse_rubric(redaction.redacted_text))
    except (ProviderUnavailableError, ValueError, TypeError, AttributeError) as exc:
        manifest["status"] = "TRANSMISSION_FAILED"
        manifest["may_have_been_transmitted"] = True
        job.external_data_manifest = manifest
        job.status = AnalysisStatus.FAILED
        job.error_message = f"Rubric parsing unavailable: {type(exc).__name__}."
        job.provenance = DataProvenance.UNAVAILABLE
        job.completed_at = _utcnow()
        session.commit()
        return job

    manifest["status"] = "SENT"
    job.external_data_manifest = dict(manifest)
    try:
        output = result.parsed
        items = list(output.items)  # type: ignore[attr-defined]
        if not items:
            raise ValueError("Rubric parser returned no criteria")
        if sum(float(item.max_score) for item in items) > float(job.assignment.total_score):
            raise ValueError("Parsed rubric exceeds assignment total_score")
    except (ValueError, TypeError, AttributeError) as exc:
        job.status = AnalysisStatus.FAILED
        job.error_message = f"Rubric parsing unavailable: {type(exc).__name__}."
        job.provenance = DataProvenance.UNAVAILABLE
        job.completed_at = _utcnow()
        session.commit()
        return job

    for index, item in enumerate(items, start=1):
        rules = {
            "evaluation_type": item.evaluation_type,
            "required_evidence": item.required_evidence,
            "deduction_rules": [rule.model_dump(mode="json") for rule in item.deduction_rules],
            "partial_credit_guidance": [
                guidance.model_dump(mode="json") for guidance in item.partial_credit_guidance
            ],
        }
        session.add(
            RubricCriterion(
                assignment_id=job.assignment_id,
                criterion_key=_criterion_key(item.id, index=index, job_id=job.id),
                title=item.title,
                description=item.description,
                max_score=Decimal(str(item.max_score)),
                rules=rules,
                sort_order=index,
                origin=RubricOrigin.AI_STRUCTURED,
                approval_status=RubricStatus.DRAFT,
            )
        )
    invalidate_assignment_inputs(
        session,
        job.assignment,
        "AI-structured draft rubric items were added",
    )
    job.provider = result.provider
    job.provider_response_id = result.response_id
    job.model_name = result.resolved_model
    job.uncertainties = list(output.uncertainties)  # type: ignore[attr-defined]
    job.status = AnalysisStatus.COMPLETED
    job.provenance = DataProvenance.LIVE
    job.completed_at = _utcnow()
    session.commit()
    return job


def process_next_analysis(
    session: Session,
    *,
    provider: AnalysisProvider | None = None,
) -> bool:
    analysis_id = _claim_id(session, AIAnalysis)
    if analysis_id is None:
        return False
    process_analysis_job(session, analysis_id, provider=provider)
    return True


def process_next_rubric_parse(
    session: Session,
    *,
    provider: AnalysisProvider | None = None,
) -> bool:
    job_id = _claim_id(session, RubricParseJob)
    if job_id is None:
        return False
    process_rubric_parse_job(session, job_id, provider=provider)
    return True
