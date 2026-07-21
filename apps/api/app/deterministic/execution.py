"""Deterministic execution-result classification and safe projections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .comparison import ComparisonMode, ComparisonResult, compare_outputs
from .harness import AssignmentExecutionConfig, TestCaseSpec
from .types import EvidenceVisibility, ExecutionError, SourceCodeLocation


class ExecutionStatus(StrEnum):
    PASSED = "PASSED"
    WRONG_ANSWER = "WRONG_ANSWER"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIMEOUT = "TIMEOUT"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNAVAILABLE = "UNAVAILABLE"


class RunnerPhaseStatus(StrEnum):
    COMPLETED = "COMPLETED"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIMEOUT = "TIMEOUT"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ResultAudience(StrEnum):
    SYSTEM = "SYSTEM"
    REVIEWER = "REVIEWER"
    STUDENT = "STUDENT"
    EXTERNAL_AI = "EXTERNAL_AI"
    CSV = "CSV"


@dataclass(frozen=True, slots=True)
class RawTestExecution:
    test_case_id: str
    phase_status: RunnerPhaseStatus
    actual_output: str = ""
    captured_stdout: str = ""
    stderr: str = ""
    execution_time_ms: int = 0
    exit_code: int | None = None
    exception_type: str | None = None
    error_message: str | None = None
    error_line: int | None = None
    output_truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase_status", RunnerPhaseStatus(self.phase_status))


@dataclass(frozen=True, slots=True)
class TestExecutionResult:
    test_case_id: str
    status: ExecutionStatus
    input_value: Any
    expected_output: Any
    actual_output: str
    stderr: str
    execution_time_ms: int
    exit_code: int | None
    comparison_mode: ComparisonMode
    visibility: EvidenceVisibility
    captured_stdout: str = ""
    comparison: ComparisonResult | None = None
    error: ExecutionError | None = None
    output_truncated: bool = False

    @property
    def primary_evidence_type(self) -> str:
        return "TestResult"

    def as_view(self, audience: ResultAudience | str) -> dict[str, Any]:
        """Project a result without leaking hidden inputs or answers."""

        selected = ResultAudience(audience)
        can_see_sensitive = selected is ResultAudience.SYSTEM
        if selected is ResultAudience.REVIEWER:
            can_see_sensitive = self.visibility is not EvidenceVisibility.INTERNAL
        elif selected is ResultAudience.STUDENT:
            can_see_sensitive = self.visibility is EvidenceVisibility.STUDENT_VISIBLE
        return {
            "test_case_id": self.test_case_id,
            "status": self.status.value,
            "input": self.input_value if can_see_sensitive else None,
            "expected_output": self.expected_output if can_see_sensitive else None,
            # Hidden input is often echoed by student code, so actual output and
            # stderr are masked with the input/answer rather than assumed safe.
            "actual_output": self.actual_output if can_see_sensitive else None,
            "stdout": self.captured_stdout if can_see_sensitive else "",
            "stderr": self.stderr if can_see_sensitive else "",
            "execution_time_ms": self.execution_time_ms,
            "exit_code": self.exit_code,
            "comparison_mode": self.comparison_mode.value,
            "visibility": self.visibility.value,
            "output_truncated": self.output_truncated,
        }


def _sanitize_message(message: str | None, limit: int = 500) -> str:
    if not message:
        return "Execution failed without a diagnostic message."
    # Remove Unix/Windows absolute paths and collapse a traceback to one line.
    sanitized = re.sub(r"(?:[A-Za-z]:\\|/)[^\s:]+", "<path>", message)
    sanitized = " ".join(sanitized.split())
    return sanitized[:limit]


def classify_syntax(
    source_code: str, *, filename: str = "submission.py"
) -> ExecutionError | None:
    """Compile without executing and return a sanitized syntax observation."""

    try:
        compile(source_code, filename, "exec", dont_inherit=True)
    except SyntaxError as exc:
        location = SourceCodeLocation(
            file=filename,
            line_start=max(1, exc.lineno or 1),
            line_end=max(1, exc.end_lineno or exc.lineno or 1),
            column_start=max(0, (exc.offset or 1) - 1),
            column_end=max(0, (exc.end_offset or exc.offset or 1) - 1),
        )
        return ExecutionError(
            category=ExecutionStatus.SYNTAX_ERROR.value,
            exception_type="SyntaxError",
            message=exc.msg,
            location=location,
        )
    return None


def classify_test_execution(
    raw: RawTestExecution,
    test: TestCaseSpec,
    config: AssignmentExecutionConfig,
    *,
    source_filename: str = "submission.py",
) -> TestExecutionResult:
    policy = test.applied_policy(config)
    status_map = {
        RunnerPhaseStatus.SYNTAX_ERROR: ExecutionStatus.SYNTAX_ERROR,
        RunnerPhaseStatus.RUNTIME_ERROR: ExecutionStatus.RUNTIME_ERROR,
        RunnerPhaseStatus.TIMEOUT: ExecutionStatus.TIMEOUT,
        RunnerPhaseStatus.SECURITY_VIOLATION: ExecutionStatus.SECURITY_VIOLATION,
        RunnerPhaseStatus.INTERNAL_ERROR: ExecutionStatus.INTERNAL_ERROR,
    }
    comparison = None
    error = None
    if raw.phase_status is RunnerPhaseStatus.COMPLETED:
        comparison = compare_outputs(test.expected_output, raw.actual_output, policy)
        status = (
            ExecutionStatus.PASSED if comparison.matched else ExecutionStatus.WRONG_ANSWER
        )
    else:
        status = status_map[raw.phase_status]
        location = (
            SourceCodeLocation(
                file=source_filename,
                line_start=raw.error_line,
                line_end=raw.error_line,
            )
            if raw.error_line and raw.error_line > 0
            else None
        )
        error = ExecutionError(
            category=status.value,
            exception_type=raw.exception_type,
            message=_sanitize_message(raw.error_message or raw.stderr),
            location=location,
        )

    return TestExecutionResult(
        test_case_id=test.test_case_id,
        status=status,
        input_value=test.input_data,
        expected_output=test.expected_output,
        actual_output=raw.actual_output,
        stderr=_sanitize_message(raw.stderr, 2_000) if raw.stderr else "",
        execution_time_ms=max(0, raw.execution_time_ms),
        exit_code=raw.exit_code,
        comparison_mode=policy,
        visibility=test.visibility,
        captured_stdout=raw.captured_stdout,
        comparison=comparison,
        error=error,
        output_truncated=raw.output_truncated,
    )
