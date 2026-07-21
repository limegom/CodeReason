"""Persist and run deterministic submission jobs.

API requests enqueue ``ExecutionRun`` records. The worker builds sandbox requests
from persisted inputs and stores observed results; Docker failures do not produce
synthetic test results.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from typing import Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.deterministic.ast_analysis import ASTAnalysisReport, analyze_python_source
from app.deterministic.comparison import ComparisonMode as DeterministicComparisonMode
from app.deterministic.docker_sandbox import (
    SANDBOX_IMAGE,
    DockerSandbox,
    SandboxExecutionResult,
    SandboxRequest,
)
from app.deterministic.execution import (
    ExecutionStatus as DeterministicExecutionStatus,
    TestExecutionResult,
)
from app.deterministic.harness import (
    AssignmentExecutionConfig,
    ExecutionMode as DeterministicExecutionMode,
    FunctionArguments,
    TestCaseSpec,
)
from app.deterministic.types import EvidenceVisibility as DeterministicVisibility
from app.models import (
    ComparisonMode,
    DataProvenance,
    ErrorCategory,
    Evidence,
    EvidenceKind,
    EvidenceVisibility,
    ExecutionMode,
    ExecutionRun,
    ExecutionStatus,
    SourceFile,
    Submission,
    SubmissionStatus,
    TestCase,
    TestResult,
    TestResultStatus,
)


logger = logging.getLogger("codereason.execution")

RUNNER_VERSION = "codereason-deterministic-v1"


class SandboxExecutor(Protocol):
    def execute(self, request: SandboxRequest) -> SandboxExecutionResult: ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(kind: str, details: Mapping[str, object]) -> str:
    canonical = json.dumps(
        {"kind": kind, "details": details},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _db_visibility(value: DeterministicVisibility) -> EvidenceVisibility:
    return EvidenceVisibility(value.value)


def _deterministic_visibility(test_case: TestCase) -> DeterministicVisibility:
    return (
        DeterministicVisibility.REVIEWER_ONLY
        if test_case.is_hidden
        else DeterministicVisibility.STUDENT_VISIBLE
    )


def _harness_arguments_schema(assignment_schema: Mapping[str, object]) -> dict | None:
    """Normalize assignment schemas to the runner's ``args``/``kwargs`` envelope.

    Object schemas without ``args`` or ``kwargs`` describe keyword arguments.
    Input is never interpreted as a command or call expression.
    """

    if not assignment_schema:
        return None
    schema = dict(assignment_schema)
    schema_type = schema.get("type")
    properties = schema.get("properties")
    if schema_type == "object" and isinstance(properties, Mapping):
        property_names = set(properties)
        if property_names and property_names <= {"args", "kwargs"}:
            return schema
        return {
            "type": "object",
            "required": ["args", "kwargs"],
            "properties": {
                "args": {"type": "array", "maxItems": 0},
                "kwargs": schema,
            },
            "additionalProperties": False,
        }
    if schema_type == "array":
        return {
            "type": "object",
            "required": ["args", "kwargs"],
            "properties": {
                "args": schema,
                "kwargs": {"type": "object"},
            },
            "additionalProperties": False,
        }
    return schema


def _expected_parameters(assignment_schema: Mapping[str, object]) -> tuple[str, ...] | None:
    properties = assignment_schema.get("properties")
    if not isinstance(properties, Mapping) or not properties:
        return None
    names = tuple(str(name) for name in properties if name not in {"args", "kwargs"})
    return names or None


def _function_input(value: object) -> Mapping[str, object] | FunctionArguments:
    if isinstance(value, Mapping):
        if set(value) <= {"args", "kwargs"} and ("args" in value or "kwargs" in value):
            return dict(value)
        return {"args": [], "kwargs": dict(value)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return FunctionArguments(args=tuple(value))
    return FunctionArguments(args=(value,))


def _build_request(
    submission: Submission,
    source_file: SourceFile,
    test_cases: Sequence[TestCase],
) -> SandboxRequest:
    assignment = submission.assignment
    mode = DeterministicExecutionMode(assignment.execution_mode.value)
    config = AssignmentExecutionConfig(
        execution_mode=mode,
        entry_function=assignment.entry_function,
        comparison_mode=DeterministicComparisonMode(assignment.comparison_mode.value),
        arguments_schema=(
            _harness_arguments_schema(assignment.arguments_schema)
            if mode is DeterministicExecutionMode.FUNCTION
            else None
        ),
    )
    tests = tuple(
        TestCaseSpec(
            test_case_id=test_case.id,
            input_data=(
                _function_input(test_case.input_payload)
                if mode is DeterministicExecutionMode.FUNCTION
                else test_case.input_payload
            ),
            expected_output=test_case.expected_output,
            comparison_mode=(
                DeterministicComparisonMode(test_case.comparison_mode.value)
                if test_case.comparison_mode is not None
                else None
            ),
            visibility=_deterministic_visibility(test_case),
        )
        for test_case in test_cases
    )
    return SandboxRequest(
        source_code=source_file.content,
        source_filename=source_file.filename,
        config=config,
        tests=tests,
        per_test_timeout_ms=assignment.time_limit_ms,
    )


def _signature_status(report: ASTAnalysisReport, execution_mode: ExecutionMode) -> str:
    if execution_mode == ExecutionMode.STDIN_STDOUT:
        return "NOT_APPLICABLE"
    features = report.feature_summary()
    if features.get("syntax_valid") is False:
        return "UNAVAILABLE_SYNTAX_ERROR"
    if features.get("expected_function_exists") is False:
        return "MISSING_FUNCTION"
    if features.get("signature_matches") is True:
        return "MATCHES"
    if features.get("signature_matches") is False:
        return "MISMATCH"
    return "FUNCTION_PRESENT"


def _error_category(status: DeterministicExecutionStatus) -> ErrorCategory | None:
    if status is DeterministicExecutionStatus.PASSED:
        return None
    mapping = {
        DeterministicExecutionStatus.WRONG_ANSWER: ErrorCategory.WRONG_ANSWER,
        DeterministicExecutionStatus.SYNTAX_ERROR: ErrorCategory.SYNTAX_ERROR,
        DeterministicExecutionStatus.RUNTIME_ERROR: ErrorCategory.RUNTIME_ERROR,
        DeterministicExecutionStatus.TIMEOUT: ErrorCategory.TIMEOUT,
        DeterministicExecutionStatus.SECURITY_VIOLATION: ErrorCategory.SECURITY_VIOLATION,
        DeterministicExecutionStatus.INTERNAL_ERROR: ErrorCategory.INTERNAL_ERROR,
        DeterministicExecutionStatus.UNAVAILABLE: ErrorCategory.EXECUTION_UNAVAILABLE,
    }
    return mapping[status]


def _test_status(status: DeterministicExecutionStatus) -> TestResultStatus:
    if status is DeterministicExecutionStatus.PASSED:
        return TestResultStatus.PASSED
    if status is DeterministicExecutionStatus.WRONG_ANSWER:
        return TestResultStatus.FAILED
    if status is DeterministicExecutionStatus.TIMEOUT:
        return TestResultStatus.TIMED_OUT
    return TestResultStatus.ERROR


def _run_status(status: DeterministicExecutionStatus) -> ExecutionStatus:
    if status in {
        DeterministicExecutionStatus.PASSED,
        DeterministicExecutionStatus.WRONG_ANSWER,
    }:
        return ExecutionStatus.COMPLETED
    if status is DeterministicExecutionStatus.TIMEOUT:
        return ExecutionStatus.TIMED_OUT
    if status is DeterministicExecutionStatus.UNAVAILABLE:
        return ExecutionStatus.UNAVAILABLE
    return ExecutionStatus.FAILED


def _persist_ast_evidence(
    session: Session,
    *,
    run: ExecutionRun,
    source_file: SourceFile,
    report: ASTAnalysisReport,
) -> None:
    for finding in report.ast_findings:
        details: dict[str, object] = {
            "rule": finding.rule,
            "passed": finding.passed,
            **finding.details,
        }
        session.add(
            Evidence(
                submission_id=run.submission_id,
                execution_run_id=run.id,
                source_file_id=source_file.id,
                kind=EvidenceKind.AST_FINDING,
                visibility=_db_visibility(finding.visibility),
                summary=finding.message,
                details=details,
                start_line=finding.location.line_start if finding.location else None,
                end_line=finding.location.line_end if finding.location else None,
                fingerprint=_fingerprint(EvidenceKind.AST_FINDING.value, details),
                provenance=DataProvenance.LIVE,
            )
        )
    for finding in report.static_findings:
        details = {
            "rule": finding.rule,
            "severity": finding.severity.value,
            **finding.details,
        }
        session.add(
            Evidence(
                submission_id=run.submission_id,
                execution_run_id=run.id,
                source_file_id=source_file.id,
                kind=EvidenceKind.STATIC_FINDING,
                visibility=_db_visibility(finding.visibility),
                summary=finding.message,
                details=details,
                start_line=finding.location.line_start if finding.location else None,
                end_line=finding.location.line_end if finding.location else None,
                fingerprint=_fingerprint(EvidenceKind.STATIC_FINDING.value, details),
                provenance=DataProvenance.LIVE,
            )
        )
    if report.syntax_error is not None:
        error = report.syntax_error
        details = {
            "category": error.category,
            "exception_type": error.exception_type,
        }
        session.add(
            Evidence(
                submission_id=run.submission_id,
                execution_run_id=run.id,
                source_file_id=source_file.id,
                kind=EvidenceKind.EXECUTION_ERROR,
                visibility=_db_visibility(error.visibility),
                summary=error.message,
                details=details,
                start_line=error.location.line_start if error.location else None,
                end_line=error.location.line_end if error.location else None,
                fingerprint=_fingerprint(EvidenceKind.EXECUTION_ERROR.value, details),
                provenance=DataProvenance.LIVE,
            )
        )


def _persist_test_result(
    session: Session,
    *,
    run: ExecutionRun,
    source_file: SourceFile,
    test_case: TestCase,
    result: TestExecutionResult,
) -> None:
    category = _error_category(result.status)
    test_result = TestResult(
        execution_run_id=run.id,
        test_case_id=result.test_case_id,
        status=_test_status(result.status),
        applied_comparison_mode=ComparisonMode(result.comparison_mode.value),
        actual_output=result.actual_output,
        stderr=result.stderr,
        exit_code=result.exit_code,
        error_category=category,
        duration_ms=float(result.execution_time_ms),
        result_metadata={
            "captured_stdout": result.captured_stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "output_truncated": result.output_truncated,
        },
    )
    session.add(test_result)
    session.flush()

    # Visibility comes from the persisted test definition, never from runner
    # output, so a malformed adapter cannot make a hidden result student-visible.
    visibility = _db_visibility(_deterministic_visibility(test_case))
    details: dict[str, object] = {
        "status": result.status.value,
        "comparison_mode": result.comparison_mode.value,
        "error_category": category.value if category else None,
        "duration_ms": result.execution_time_ms,
        "output_truncated": result.output_truncated,
    }
    session.add(
        Evidence(
            submission_id=run.submission_id,
            execution_run_id=run.id,
            test_result_id=test_result.id,
            kind=EvidenceKind.TEST_RESULT,
            visibility=visibility,
            summary=(
                f"Test {result.test_case_id!r} completed with status {result.status.value} "
                f"using {result.comparison_mode.value}."
            ),
            details=details,
            fingerprint=_fingerprint(EvidenceKind.TEST_RESULT.value, details),
            provenance=DataProvenance.LIVE,
        )
    )

    if result.error is not None:
        error = result.error
        error_details = {
            "category": error.category,
            "exception_type": error.exception_type,
        }
        session.add(
            Evidence(
                submission_id=run.submission_id,
                execution_run_id=run.id,
                test_result_id=test_result.id,
                source_file_id=source_file.id if error.location else None,
                kind=EvidenceKind.EXECUTION_ERROR,
                visibility=visibility,
                summary=error.message,
                details=error_details,
                start_line=error.location.line_start if error.location else None,
                end_line=error.location.line_end if error.location else None,
                fingerprint=_fingerprint(EvidenceKind.EXECUTION_ERROR.value, error_details),
                provenance=DataProvenance.LIVE,
            )
        )


def claim_pending_execution(session: Session) -> str | None:
    """Atomically claim the oldest pending execution job, if one exists."""

    cutoff = _utcnow() - timedelta(minutes=5)
    abandoned = session.scalars(
        select(ExecutionRun).where(
            ExecutionRun.status == ExecutionStatus.RUNNING,
            ExecutionRun.started_at.is_not(None),
            ExecutionRun.started_at < cutoff,
        )
    ).all()
    for stale_run in abandoned:
        stale_run.status = ExecutionStatus.PENDING
        stale_run.started_at = None
        stale_run.run_metadata = {
            **dict(stale_run.run_metadata or {}),
            "reclaimed_after_abandoned_worker": True,
        }
        stale_run.submission.status = SubmissionStatus.QUEUED
    if abandoned:
        session.commit()

    candidate_id = session.scalar(
        select(ExecutionRun.id)
        .where(ExecutionRun.status == ExecutionStatus.PENDING)
        .order_by(ExecutionRun.created_at, ExecutionRun.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if candidate_id is None:
        session.rollback()
        return None

    now = _utcnow()
    pending_run = session.get(ExecutionRun, candidate_id)
    trusted_auto_analyze = bool(
        pending_run and pending_run.run_metadata.get("auto_analyze") is True
    )
    requested_via = (
        str(pending_run.run_metadata.get("requested_via", "API"))
        if pending_run
        else "API"
    )
    claimed = session.execute(
        update(ExecutionRun)
        .where(
            ExecutionRun.id == candidate_id,
            ExecutionRun.status == ExecutionStatus.PENDING,
        )
        .values(
            status=ExecutionStatus.RUNNING,
            runner_version=RUNNER_VERSION,
            image_digest=None,
            started_at=now,
            completed_at=None,
            error_category=None,
            exception_type=None,
            signature_status=None,
            run_metadata={
                "job_type": "EXECUTION",
                "claimed_at": now.isoformat(),
                "provenance": "PENDING",
                "auto_analyze": trusted_auto_analyze,
                "requested_via": requested_via,
            },
        )
    )
    if claimed.rowcount != 1:
        session.rollback()
        return None

    run = session.get(ExecutionRun, candidate_id)
    if run is not None:
        submission = session.get(Submission, run.submission_id)
        if submission is not None:
            submission.status = SubmissionStatus.ANALYZING
    session.commit()
    return candidate_id


def _mark_orchestration_failure(
    session: Session,
    run_id: str,
    *,
    reason: str,
    exception_type: str | None = None,
) -> None:
    run = session.get(ExecutionRun, run_id)
    if run is None:
        return
    now = _utcnow()
    run.status = ExecutionStatus.FAILED
    run.provenance = DataProvenance.UNAVAILABLE
    run.error_category = ErrorCategory.INTERNAL_ERROR
    run.exception_type = exception_type
    run.signature_status = "UNAVAILABLE"
    run.completed_at = now
    run.run_metadata = {
        "job_type": "EXECUTION",
        "provenance": "UNAVAILABLE",
        "execution_available": False,
        "failure_reason": reason,
        "test_status_vector": [],
        "ast_feature_summary": {},
        "error_category": ErrorCategory.INTERNAL_ERROR.value,
        "exception_type": exception_type,
        "signature_status": "UNAVAILABLE",
        "sandbox_image": SANDBOX_IMAGE,
        "completed_at": now.isoformat(),
    }
    run.submission.status = SubmissionStatus.FAILED
    session.commit()


def execute_claimed_run(
    session: Session,
    run_id: str,
    *,
    sandbox: SandboxExecutor | None = None,
) -> ExecutionRun:
    """Execute one already-claimed run and persist deterministic observations."""

    run = session.get(ExecutionRun, run_id)
    if run is None:
        raise LookupError(f"ExecutionRun {run_id} does not exist")
    if run.status != ExecutionStatus.RUNNING:
        raise ValueError("only a RUNNING execution can be processed")

    submission = run.submission
    assignment = submission.assignment
    if (
        run.assignment_input_version != assignment.analysis_input_version
        or (run.source_version != 0 and run.source_version != submission.source_version)
    ):
        _mark_orchestration_failure(session, run.id, reason="stale_execution_input")
        return session.get(ExecutionRun, run.id)  # type: ignore[return-value]
    current_sources = list(
        session.scalars(
            select(SourceFile)
            .where(
                SourceFile.submission_id == submission.id,
                SourceFile.is_current.is_(True),
            )
            .order_by(SourceFile.revision.desc(), SourceFile.filename)
        )
    )
    if len(current_sources) != 1:
        reason = "current_source_missing" if not current_sources else "multiple_current_sources"
        _mark_orchestration_failure(session, run.id, reason=reason)
        return session.get(ExecutionRun, run.id)  # type: ignore[return-value]
    source_file = current_sources[0]

    test_cases = list(
        session.scalars(
            select(TestCase)
            .where(TestCase.assignment_id == assignment.id, TestCase.active.is_(True))
            .order_by(TestCase.sort_order, TestCase.created_at, TestCase.id)
        )
    )
    if not test_cases:
        _mark_orchestration_failure(session, run.id, reason="active_test_cases_missing")
        return session.get(ExecutionRun, run.id)  # type: ignore[return-value]

    # Discard run-scoped artifacts before retrying a pending job.
    session.execute(delete(Evidence).where(Evidence.execution_run_id == run.id))
    session.execute(delete(TestResult).where(TestResult.execution_run_id == run.id))

    expected_parameters = (
        _expected_parameters(assignment.arguments_schema)
        if assignment.execution_mode == ExecutionMode.FUNCTION
        else None
    )
    report = analyze_python_source(
        source_file.content,
        filename=source_file.filename,
        expected_function=assignment.entry_function,
        expected_parameters=expected_parameters,
    )
    _persist_ast_evidence(
        session,
        run=run,
        source_file=source_file,
        report=report,
    )

    request = _build_request(submission, source_file, test_cases)
    result = (sandbox or DockerSandbox()).execute(request)
    expected_test_ids = [test_case.id for test_case in test_cases]
    observed_test_ids = [item.test_case_id for item in result.test_results]
    if result.status is DeterministicExecutionStatus.UNAVAILABLE:
        if observed_test_ids:
            raise ValueError("an unavailable sandbox must not return test results")
    elif observed_test_ids != expected_test_ids:
        raise ValueError("sandbox results must cover active tests exactly once and in order")
    test_cases_by_id = {test_case.id: test_case for test_case in test_cases}
    for test_result in result.test_results:
        _persist_test_result(
            session,
            run=run,
            source_file=source_file,
            test_case=test_cases_by_id[test_result.test_case_id],
            result=test_result,
        )

    signature_status = _signature_status(report, assignment.execution_mode)
    test_status_vector = [item.status.value for item in result.test_results]
    category = _error_category(result.status)
    exception_type = next(
        (
            item.error.exception_type
            for item in result.test_results
            if item.error is not None and item.error.exception_type
        ),
        report.syntax_error.exception_type if report.syntax_error else None,
    )
    execution_available = result.status is not DeterministicExecutionStatus.UNAVAILABLE
    provenance = "LIVE" if execution_available else "UNAVAILABLE"
    auto_analyze = run.run_metadata.get("auto_analyze") is True
    requested_via = str(run.run_metadata.get("requested_via", "API"))
    now = _utcnow()

    run.status = _run_status(result.status)
    run.provenance = (
        DataProvenance.LIVE if execution_available else DataProvenance.UNAVAILABLE
    )
    run.error_category = category
    run.exception_type = exception_type
    run.signature_status = signature_status
    run.completed_at = now
    run.run_metadata = {
        "job_type": "EXECUTION",
        "provenance": provenance,
        "auto_analyze": auto_analyze,
        "requested_via": requested_via,
        "execution_available": execution_available,
        "sandbox_image": SANDBOX_IMAGE,
        "runner_version": RUNNER_VERSION,
        "assignment_input_version": assignment.analysis_input_version,
        "source_version": submission.source_version,
        "source_file_id": source_file.id,
        "test_case_ids": [test_case.id for test_case in test_cases],
        "test_status_vector": test_status_vector,
        "ast_feature_summary": report.feature_summary(),
        "error_category": category.value if category else None,
        "exception_type": exception_type,
        "signature_status": signature_status,
        "unavailable_reason": result.unavailable_reason,
        "infrastructure_error": result.infrastructure_error,
        "completed_at": now.isoformat(),
    }
    submission.status = (
        SubmissionStatus.FAILED
        if run.status == ExecutionStatus.FAILED
        and result.status
        in {
            DeterministicExecutionStatus.INTERNAL_ERROR,
            DeterministicExecutionStatus.SECURITY_VIOLATION,
        }
        else SubmissionStatus.REVIEW_REQUIRED
    )
    session.commit()
    session.refresh(run)
    return run


def process_next_pending_execution(
    session: Session,
    *,
    sandbox: SandboxExecutor | None = None,
) -> str | None:
    """Claim and process one job; return its id, or ``None`` when idle."""

    run_id = claim_pending_execution(session)
    if run_id is None:
        return None
    try:
        execute_claimed_run(session, run_id, sandbox=sandbox)
    except Exception as exc:  # keep the durable job out of RUNNING on adapter failure
        session.rollback()
        logger.exception("Execution orchestration failed for run %s", run_id)
        _mark_orchestration_failure(
            session,
            run_id,
            reason="execution_orchestration_failed",
            exception_type=type(exc).__name__,
        )
    return run_id
