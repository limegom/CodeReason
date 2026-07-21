from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deterministic.comparison import ComparisonMode as DeterministicComparisonMode
from app.deterministic.docker_sandbox import SANDBOX_IMAGE, SandboxExecutionResult
from app.deterministic.execution import (
    ExecutionStatus as DeterministicExecutionStatus,
    TestExecutionResult as DeterministicTestExecutionResult,
)
from app.deterministic.types import EvidenceVisibility as DeterministicVisibility
from app.models import (
    Assignment,
    ComparisonMode,
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
    TestCase as DbTestCase,
    TestResult as DbTestResult,
)
from app.services.execution_orchestrator import (
    RUNNER_VERSION,
    process_next_pending_execution,
)
from tests.factories import persist


class FakeSandbox:
    def __init__(self, result: SandboxExecutionResult | Exception) -> None:
        self.result = result
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def seed_pending_run(
    db_session: Session,
) -> tuple[ExecutionRun, SourceFile, DbTestCase, DbTestCase]:
    assignment = persist(
        db_session,
        Assignment,
        title="Evidence-bound function",
        description="Return the supplied data.",
        execution_mode=ExecutionMode.FUNCTION,
        entry_function="solve",
        arguments_schema={
            "type": "object",
            "properties": {"data": {"type": "array"}},
            "required": ["data"],
        },
        comparison_mode=ComparisonMode.JSON_VALUE,
    )
    submission = persist(
        db_session,
        Submission,
        assignment_id=assignment.id,
        student_reference="opaque-student",
        status=SubmissionStatus.QUEUED,
        source_version=1,
    )
    content = "def solve(data):\n    return data\n"
    source_file = persist(
        db_session,
        SourceFile,
        submission_id=submission.id,
        filename="submission.py",
        content=content,
        content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        revision=1,
        is_current=True,
    )
    public_test = persist(
        db_session,
        DbTestCase,
        assignment_id=assignment.id,
        name="public",
        input_payload={"data": [1, 2]},
        expected_output=[1, 2],
        is_hidden=False,
        active=True,
        sort_order=0,
    )
    hidden_test = persist(
        db_session,
        DbTestCase,
        assignment_id=assignment.id,
        name="hidden",
        input_payload={"data": [7, 8]},
        expected_output=[7, 8],
        is_hidden=True,
        active=True,
        sort_order=1,
    )
    run = persist(
        db_session,
        ExecutionRun,
        submission_id=submission.id,
        status=ExecutionStatus.PENDING,
        runner_version="client-spoofed-runner",
        image_digest="client-spoofed-image",
        run_metadata={"provenance": "FIXTURE", "command": "untrusted"},
    )
    db_session.commit()
    return run, source_file, public_test, hidden_test


def test_worker_claims_and_persists_results_ast_and_visibility(db_session: Session) -> None:
    run, _, public_test, hidden_test = seed_pending_run(db_session)
    public_result = DeterministicTestExecutionResult(
        test_case_id=public_test.id,
        status=DeterministicExecutionStatus.PASSED,
        input_value={"data": [1, 2]},
        expected_output=[1, 2],
        actual_output="[1,2]",
        stderr="",
        execution_time_ms=3,
        exit_code=0,
        comparison_mode=DeterministicComparisonMode.JSON_VALUE,
        visibility=DeterministicVisibility.STUDENT_VISIBLE,
    )
    hidden_result = DeterministicTestExecutionResult(
        test_case_id=hidden_test.id,
        status=DeterministicExecutionStatus.WRONG_ANSWER,
        input_value={"data": [7, 8]},
        expected_output=[7, 8],
        actual_output="[8,7]",
        stderr="",
        execution_time_ms=4,
        exit_code=0,
        comparison_mode=DeterministicComparisonMode.JSON_VALUE,
        # Even malformed runner visibility must not override the DB hidden flag.
        visibility=DeterministicVisibility.STUDENT_VISIBLE,
    )
    sandbox = FakeSandbox(
        SandboxExecutionResult(
            status=DeterministicExecutionStatus.WRONG_ANSWER,
            test_results=(public_result, hidden_result),
        )
    )

    processed_id = process_next_pending_execution(db_session, sandbox=sandbox)

    assert processed_id == run.id
    assert len(sandbox.requests) == 1
    runner_payload = sandbox.requests[0].runner_payload()
    assert runner_payload["execution"]["entry_function"] == "solve"
    assert runner_payload["tests"][0]["input"] == {
        "args": [],
        "kwargs": {"data": [1, 2]},
    }
    assert "expected_output" not in runner_payload["tests"][0]

    db_session.expire_all()
    stored_run = db_session.get(ExecutionRun, run.id)
    assert stored_run is not None
    assert stored_run.status == ExecutionStatus.COMPLETED
    assert stored_run.runner_version == RUNNER_VERSION
    assert stored_run.image_digest is None
    assert stored_run.error_category == ErrorCategory.WRONG_ANSWER
    assert stored_run.signature_status == "MATCHES"
    assert stored_run.run_metadata["sandbox_image"] == SANDBOX_IMAGE
    assert stored_run.run_metadata["provenance"] == "LIVE"
    assert stored_run.run_metadata["test_status_vector"] == ["PASSED", "WRONG_ANSWER"]
    assert stored_run.run_metadata["ast_feature_summary"]["expected_function_exists"] is True
    assert stored_run.run_metadata["ast_feature_summary"]["signature_matches"] is True
    assert "command" not in stored_run.run_metadata
    assert stored_run.submission.status == SubmissionStatus.REVIEW_REQUIRED

    results = list(
        db_session.scalars(
            select(DbTestResult)
            .where(DbTestResult.execution_run_id == run.id)
            .order_by(DbTestResult.created_at)
        )
    )
    assert [item.test_case_id for item in results] == [public_test.id, hidden_test.id]
    assert [item.applied_comparison_mode for item in results] == [
        ComparisonMode.JSON_VALUE,
        ComparisonMode.JSON_VALUE,
    ]

    evidence = list(
        db_session.scalars(select(Evidence).where(Evidence.execution_run_id == run.id))
    )
    public_evidence = next(
        item
        for item in evidence
        if item.kind == EvidenceKind.TEST_RESULT and item.test_result_id == results[0].id
    )
    hidden_evidence = next(
        item
        for item in evidence
        if item.kind == EvidenceKind.TEST_RESULT and item.test_result_id == results[1].id
    )
    assert public_evidence.visibility == EvidenceVisibility.STUDENT_VISIBLE
    assert hidden_evidence.visibility == EvidenceVisibility.REVIEWER_ONLY
    assert "actual_output" not in hidden_evidence.details
    assert "expected_output" not in hidden_evidence.details
    assert any(item.kind == EvidenceKind.AST_FINDING for item in evidence)


def test_docker_unavailable_is_explicit_and_creates_no_fake_test_results(
    db_session: Session,
) -> None:
    run, _, _, _ = seed_pending_run(db_session)
    sandbox = FakeSandbox(
        SandboxExecutionResult(
            status=DeterministicExecutionStatus.UNAVAILABLE,
            unavailable_reason="docker_daemon_unavailable",
        )
    )

    process_next_pending_execution(db_session, sandbox=sandbox)

    db_session.expire_all()
    stored_run = db_session.get(ExecutionRun, run.id)
    assert stored_run is not None
    assert stored_run.status == ExecutionStatus.UNAVAILABLE
    assert stored_run.error_category == ErrorCategory.EXECUTION_UNAVAILABLE
    assert stored_run.run_metadata["execution_available"] is False
    assert stored_run.run_metadata["provenance"] == "UNAVAILABLE"
    assert stored_run.run_metadata["unavailable_reason"] == "docker_daemon_unavailable"
    assert stored_run.run_metadata["test_status_vector"] == []
    assert stored_run.submission.status == SubmissionStatus.REVIEW_REQUIRED
    assert list(
        db_session.scalars(
            select(DbTestResult).where(DbTestResult.execution_run_id == run.id)
        )
    ) == []
    # AST remains genuine Primary Evidence even when runtime execution is unavailable.
    assert db_session.scalar(
        select(Evidence).where(
            Evidence.execution_run_id == run.id,
            Evidence.kind == EvidenceKind.AST_FINDING,
        )
    ) is not None


def test_stdin_stdout_assignment_uses_text_input_without_function_schema(
    db_session: Session,
) -> None:
    assignment = persist(
        db_session,
        Assignment,
        title="Echo",
        description="Echo stdin.",
        execution_mode=ExecutionMode.STDIN_STDOUT,
        entry_function=None,
        # The API permits this descriptive schema, but it must never be treated
        # as a function-call schema by the runner.
        arguments_schema={"type": "string"},
        comparison_mode=ComparisonMode.IGNORE_FINAL_NEWLINE,
    )
    submission = persist(
        db_session,
        Submission,
        assignment_id=assignment.id,
        student_reference="opaque-stdin",
        status=SubmissionStatus.QUEUED,
        source_version=1,
    )
    content = "print(input())\n"
    persist(
        db_session,
        SourceFile,
        submission_id=submission.id,
        filename="echo.py",
        content=content,
        content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        revision=1,
        is_current=True,
    )
    test_case = persist(
        db_session,
        DbTestCase,
        assignment_id=assignment.id,
        name="echo public",
        input_payload="hello\n",
        expected_output="hello\n",
        is_hidden=False,
        active=True,
    )
    run = persist(
        db_session,
        ExecutionRun,
        submission_id=submission.id,
        status=ExecutionStatus.PENDING,
        runner_version="pending",
    )
    db_session.commit()
    sandbox = FakeSandbox(
        SandboxExecutionResult(
            status=DeterministicExecutionStatus.PASSED,
            test_results=(
                DeterministicTestExecutionResult(
                    test_case_id=test_case.id,
                    status=DeterministicExecutionStatus.PASSED,
                    input_value="hello\n",
                    expected_output="hello\n",
                    actual_output="hello\n",
                    stderr="",
                    execution_time_ms=2,
                    exit_code=0,
                    comparison_mode=DeterministicComparisonMode.IGNORE_FINAL_NEWLINE,
                    visibility=DeterministicVisibility.STUDENT_VISIBLE,
                ),
            ),
        )
    )

    process_next_pending_execution(db_session, sandbox=sandbox)

    assert sandbox.requests[0].runner_payload()["tests"][0]["input"] == "hello\n"
    db_session.expire_all()
    stored_run = db_session.get(ExecutionRun, run.id)
    assert stored_run is not None
    assert stored_run.status == ExecutionStatus.COMPLETED
    assert stored_run.signature_status == "NOT_APPLICABLE"


def test_unexpected_sandbox_error_durably_fails_run_without_results(db_session: Session) -> None:
    run, _, _, _ = seed_pending_run(db_session)
    sandbox = FakeSandbox(RuntimeError("sensitive adapter detail must not be persisted"))

    process_next_pending_execution(db_session, sandbox=sandbox)

    db_session.expire_all()
    stored_run = db_session.get(ExecutionRun, run.id)
    assert stored_run is not None
    assert stored_run.status == ExecutionStatus.FAILED
    assert stored_run.error_category == ErrorCategory.INTERNAL_ERROR
    assert stored_run.exception_type == "RuntimeError"
    assert stored_run.run_metadata["failure_reason"] == "execution_orchestration_failed"
    assert "sensitive adapter detail" not in str(stored_run.run_metadata)
    assert stored_run.submission.status == SubmissionStatus.FAILED
    assert list(
        db_session.scalars(
            select(DbTestResult).where(DbTestResult.execution_run_id == run.id)
        )
    ) == []


def test_incomplete_runner_payload_is_rejected_without_partial_results(
    db_session: Session,
) -> None:
    run, _, public_test, _ = seed_pending_run(db_session)
    incomplete_result = DeterministicTestExecutionResult(
        test_case_id=public_test.id,
        status=DeterministicExecutionStatus.PASSED,
        input_value={"data": [1, 2]},
        expected_output=[1, 2],
        actual_output="[1,2]",
        stderr="",
        execution_time_ms=3,
        exit_code=0,
        comparison_mode=DeterministicComparisonMode.JSON_VALUE,
        visibility=DeterministicVisibility.STUDENT_VISIBLE,
    )
    sandbox = FakeSandbox(
        SandboxExecutionResult(
            status=DeterministicExecutionStatus.PASSED,
            test_results=(incomplete_result,),
        )
    )

    process_next_pending_execution(db_session, sandbox=sandbox)

    db_session.expire_all()
    stored_run = db_session.get(ExecutionRun, run.id)
    assert stored_run is not None
    assert stored_run.status == ExecutionStatus.FAILED
    assert stored_run.exception_type == "ValueError"
    assert list(
        db_session.scalars(
            select(DbTestResult).where(DbTestResult.execution_run_id == run.id)
        )
    ) == []


def test_idle_poll_does_not_call_sandbox(db_session: Session) -> None:
    sandbox = FakeSandbox(
        SandboxExecutionResult(status=DeterministicExecutionStatus.PASSED)
    )

    assert process_next_pending_execution(db_session, sandbox=sandbox) is None
    assert sandbox.requests == []
