from __future__ import annotations

from app.deterministic.comparison import ComparisonMode
from app.deterministic.execution import (
    ExecutionStatus,
    RawTestExecution,
    ResultAudience,
    RunnerPhaseStatus,
    classify_syntax,
    classify_test_execution,
)
from app.deterministic.harness import AssignmentExecutionConfig, ExecutionMode, TestCaseSpec
from app.deterministic.types import EvidenceVisibility


def test_syntax_and_runtime_errors_remain_distinct():
    syntax = classify_syntax("def broken(:\n    pass\n")
    assert syntax and syntax.category == "SYNTAX_ERROR"

    config = AssignmentExecutionConfig(ExecutionMode.STDIN_STDOUT, ComparisonMode.EXACT)
    test = TestCaseSpec("runtime", "", "ok")
    result = classify_test_execution(
        RawTestExecution(
            test_case_id="runtime",
            phase_status=RunnerPhaseStatus.RUNTIME_ERROR,
            stderr="Traceback ... IndexError: list index out of range",
            exception_type="IndexError",
            error_message="list index out of range",
            error_line=3,
            exit_code=1,
        ),
        test,
        config,
    )
    assert result.status is ExecutionStatus.RUNTIME_ERROR
    assert result.error and result.error.exception_type == "IndexError"


def test_test_result_records_policy_actually_used():
    config = AssignmentExecutionConfig(
        ExecutionMode.STDIN_STDOUT,
        ComparisonMode.EXACT,
    )
    test = TestCaseSpec(
        "tokens",
        "",
        "1 2 3",
        comparison_mode=ComparisonMode.TOKEN_BASED,
    )
    result = classify_test_execution(
        RawTestExecution("tokens", RunnerPhaseStatus.COMPLETED, actual_output="1\n2\t3"),
        test,
        config,
    )

    assert result.status is ExecutionStatus.PASSED
    assert result.comparison_mode is ComparisonMode.TOKEN_BASED


def test_hidden_test_inputs_and_answers_are_not_student_or_csv_visible():
    config = AssignmentExecutionConfig(ExecutionMode.STDIN_STDOUT, ComparisonMode.EXACT)
    test = TestCaseSpec(
        "hidden-1",
        "secret input",
        "secret expected",
        visibility=EvidenceVisibility.REVIEWER_ONLY,
    )
    result = classify_test_execution(
        RawTestExecution(
            "hidden-1",
            RunnerPhaseStatus.COMPLETED,
            actual_output="wrong",
            captured_stdout="debug secret input",
        ),
        test,
        config,
    )

    assert result.as_view(ResultAudience.REVIEWER)["expected_output"] == "secret expected"
    assert result.as_view(ResultAudience.REVIEWER)["stdout"] == "debug secret input"
    assert result.as_view(ResultAudience.STUDENT)["input"] is None
    assert result.as_view(ResultAudience.STUDENT)["expected_output"] is None
    assert result.as_view(ResultAudience.STUDENT)["actual_output"] is None
    assert result.as_view(ResultAudience.STUDENT)["stderr"] == ""
    assert result.as_view(ResultAudience.STUDENT)["stdout"] == ""
    assert result.as_view(ResultAudience.CSV)["input"] is None
    assert result.as_view(ResultAudience.CSV)["expected_output"] is None
    assert result.as_view(ResultAudience.EXTERNAL_AI)["input"] is None
    assert result.as_view(ResultAudience.EXTERNAL_AI)["expected_output"] is None
