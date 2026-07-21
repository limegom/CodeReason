"""Validated data contract sent to the fixed sandbox runner."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePath
from typing import Any, Mapping, Sequence

from .comparison import ComparisonMode
from .types import EvidenceVisibility


class ExecutionMode(StrEnum):
    FUNCTION = "FUNCTION"
    STDIN_STDOUT = "STDIN_STDOUT"


class HarnessValidationError(ValueError):
    pass


_IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class AssignmentExecutionConfig:
    execution_mode: ExecutionMode
    comparison_mode: ComparisonMode
    entry_function: str | None = None
    arguments_schema: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_mode", ExecutionMode(self.execution_mode))
        object.__setattr__(self, "comparison_mode", ComparisonMode(self.comparison_mode))
        if self.execution_mode is ExecutionMode.FUNCTION:
            if not self.entry_function or not _IDENTIFIER.fullmatch(self.entry_function):
                raise HarnessValidationError(
                    "FUNCTION mode requires a valid Python entry_function"
                )
        elif self.entry_function is not None:
            raise HarnessValidationError(
                "STDIN_STDOUT mode must not define entry_function"
            )
        if self.execution_mode is ExecutionMode.STDIN_STDOUT and self.arguments_schema:
            raise HarnessValidationError(
                "arguments_schema is only valid for FUNCTION mode"
            )
        if self.arguments_schema is not None and not isinstance(
            self.arguments_schema, Mapping
        ):
            raise HarnessValidationError("arguments_schema must be an object")


@dataclass(frozen=True, slots=True)
class FunctionArguments:
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)

    def as_json_value(self) -> dict[str, Any]:
        return {"args": list(self.args), "kwargs": dict(self.kwargs)}


@dataclass(frozen=True, slots=True)
class TestCaseSpec:
    __test__ = False

    test_case_id: str
    input_data: str | FunctionArguments | Mapping[str, Any]
    expected_output: Any
    comparison_mode: ComparisonMode | None = None
    visibility: EvidenceVisibility = EvidenceVisibility.STUDENT_VISIBLE

    def __post_init__(self) -> None:
        if not self.test_case_id or len(self.test_case_id) > 128:
            raise HarnessValidationError("test_case_id must be 1-128 characters")
        if self.comparison_mode is not None:
            object.__setattr__(
                self, "comparison_mode", ComparisonMode(self.comparison_mode)
            )
        object.__setattr__(self, "visibility", EvidenceVisibility(self.visibility))

    def applied_policy(self, config: AssignmentExecutionConfig) -> ComparisonMode:
        return self.comparison_mode or config.comparison_mode


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    """Validate the JSON Schema subset understood by the sandbox runner.

    Unsupported keywords are ignored and must not be used as execution
    constraints.
    """

    expected_type = schema.get("type")
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
    }
    if expected_type in type_map:
        expected_python_type = type_map[expected_type]
        valid = isinstance(value, expected_python_type)
        if expected_type in {"integer", "number"} and isinstance(value, bool):
            valid = False
        if not valid:
            raise HarnessValidationError(f"{path} must be {expected_type}")

    if "enum" in schema and value not in schema["enum"]:
        raise HarnessValidationError(f"{path} is not an allowed enum value")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise HarnessValidationError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise HarnessValidationError(f"{path}.{key} is not allowed")
    elif isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise HarnessValidationError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise HarnessValidationError(f"{path} has too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, f"{path}[{index}]")


def normalize_test_input(
    config: AssignmentExecutionConfig, test: TestCaseSpec
) -> str | dict[str, Any]:
    if config.execution_mode is ExecutionMode.STDIN_STDOUT:
        if not isinstance(test.input_data, str):
            raise HarnessValidationError("STDIN_STDOUT test input must be text")
        return test.input_data

    if isinstance(test.input_data, FunctionArguments):
        normalized = test.input_data.as_json_value()
    elif isinstance(test.input_data, Mapping):
        unexpected = set(test.input_data) - {"args", "kwargs"}
        if unexpected:
            raise HarnessValidationError(
                "FUNCTION input only accepts args and kwargs keys"
            )
        args = test.input_data.get("args", [])
        kwargs = test.input_data.get("kwargs", {})
        if not isinstance(args, Sequence) or isinstance(args, (str, bytes)):
            raise HarnessValidationError("FUNCTION args must be an array")
        if not isinstance(kwargs, Mapping) or not all(
            isinstance(key, str) for key in kwargs
        ):
            raise HarnessValidationError("FUNCTION kwargs must be an object")
        normalized = {"args": list(args), "kwargs": dict(kwargs)}
    else:
        raise HarnessValidationError(
            "FUNCTION input must be an {args, kwargs} object"
        )

    if config.arguments_schema:
        _validate_schema(normalized, config.arguments_schema)
    return normalized


def validate_source(source_code: str, source_filename: str) -> None:
    if not isinstance(source_code, str) or not source_code:
        raise HarnessValidationError("source_code must be non-empty text")
    if "\x00" in source_code:
        raise HarnessValidationError("source_code must not contain NUL bytes")
    if len(source_code.encode("utf-8")) > 256 * 1024:
        raise HarnessValidationError("source_code exceeds the 256 KiB limit")
    path = PurePath(source_filename)
    if (
        "/" in source_filename
        or "\\" in source_filename
        or path.name != source_filename
        or path.suffix.lower() != ".py"
    ):
        raise HarnessValidationError("source_filename must be a .py basename")


def build_runner_request(
    config: AssignmentExecutionConfig,
    tests: Sequence[TestCaseSpec],
    *,
    per_test_timeout_ms: int = 2_000,
    max_output_bytes: int = 65_536,
) -> dict[str, Any]:
    if not tests:
        raise HarnessValidationError("at least one test case is required")
    if len(tests) > 100:
        raise HarnessValidationError("at most 100 test cases are allowed")
    if not 50 <= per_test_timeout_ms <= 5_000:
        raise HarnessValidationError("per_test_timeout_ms must be 50-5000")
    if not 1_024 <= max_output_bytes <= 65_536:
        raise HarnessValidationError("max_output_bytes must be 1024-65536")
    if len({test.test_case_id for test in tests}) != len(tests):
        raise HarnessValidationError("test_case_id values must be unique")

    return {
        "version": 1,
        "execution": {
            "mode": config.execution_mode.value,
            "entry_function": config.entry_function,
            # Included for provenance; the runner never executes schema content.
            "arguments_schema": dict(config.arguments_schema or {}),
        },
        "limits": {
            "per_test_timeout_ms": per_test_timeout_ms,
            "max_output_bytes": max_output_bytes,
        },
        "tests": [
            {
                "test_case_id": test.test_case_id,
                "input": normalize_test_input(config, test),
                "comparison_mode": test.applied_policy(config).value,
            }
            for test in tests
        ],
    }
