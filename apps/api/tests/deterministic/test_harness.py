from __future__ import annotations

import pytest

from app.deterministic.comparison import ComparisonMode
from app.deterministic.harness import (
    AssignmentExecutionConfig,
    ExecutionMode,
    HarnessValidationError,
    TestCaseSpec,
    build_runner_request,
)


def test_function_mode_builds_data_only_runner_payload():
    config = AssignmentExecutionConfig(
        execution_mode=ExecutionMode.FUNCTION,
        entry_function="make_matrix",
        comparison_mode=ComparisonMode.JSON_VALUE,
        arguments_schema={
            "type": "object",
            "required": ["args", "kwargs"],
            "properties": {
                "args": {"type": "array", "minItems": 3, "maxItems": 3},
                "kwargs": {"type": "object"},
            },
            "additionalProperties": False,
        },
    )
    test = TestCaseSpec(
        test_case_id="visible-1",
        input_data={"args": [[1, 2, 3, 4], 2, 2], "kwargs": {}},
        expected_output=[[1, 2], [3, 4]],
    )

    payload = build_runner_request(config, [test])

    assert payload["execution"]["mode"] == "FUNCTION"
    assert payload["execution"]["entry_function"] == "make_matrix"
    assert payload["tests"][0]["input"]["args"][1:] == [2, 2]
    assert payload["tests"][0]["comparison_mode"] == "JSON_VALUE"
    assert "source_code" not in payload
    assert "command" not in payload
    assert "image" not in payload


def test_modes_are_not_implicitly_mixed():
    with pytest.raises(HarnessValidationError):
        AssignmentExecutionConfig(
            execution_mode=ExecutionMode.STDIN_STDOUT,
            entry_function="main",
            comparison_mode=ComparisonMode.EXACT,
        )

    config = AssignmentExecutionConfig(
        execution_mode=ExecutionMode.STDIN_STDOUT,
        comparison_mode=ComparisonMode.EXACT,
    )
    with pytest.raises(HarnessValidationError):
        build_runner_request(
            config,
            [TestCaseSpec("bad", {"args": []}, "")],
        )


def test_argument_schema_is_applied_before_sandbox_execution():
    config = AssignmentExecutionConfig(
        execution_mode=ExecutionMode.FUNCTION,
        entry_function="solve",
        comparison_mode=ComparisonMode.EXACT,
        arguments_schema={
            "type": "object",
            "properties": {"args": {"type": "array", "minItems": 2}},
        },
    )
    with pytest.raises(HarnessValidationError, match="too few"):
        build_runner_request(
            config,
            [TestCaseSpec("case", {"args": [1], "kwargs": {}}, "1")],
        )


def test_source_filename_rejects_both_path_separator_styles():
    from app.deterministic.harness import validate_source

    with pytest.raises(HarnessValidationError):
        validate_source("pass\n", "../submission.py")
    with pytest.raises(HarnessValidationError):
        validate_source("pass\n", "..\\submission.py")
