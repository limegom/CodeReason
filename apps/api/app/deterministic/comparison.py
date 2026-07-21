"""Deterministic output comparison policies."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ComparisonMode(StrEnum):
    EXACT = "EXACT"
    IGNORE_FINAL_NEWLINE = "IGNORE_FINAL_NEWLINE"
    TRIM_TRAILING_WHITESPACE = "TRIM_TRAILING_WHITESPACE"
    TOKEN_BASED = "TOKEN_BASED"
    JSON_VALUE = "JSON_VALUE"


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    matched: bool
    policy: ComparisonMode
    normalized_expected: Any
    normalized_actual: Any
    error: str | None = None


def _as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return str(value)


def _remove_one_final_newline(value: str) -> str:
    if value.endswith("\r\n"):
        return value[:-2]
    if value.endswith(("\r", "\n")):
        return value[:-1]
    return value


def _trim_trailing_whitespace(value: str) -> str:
    # Newline spelling is not material to this whitespace-tolerant policy, but
    # the number of line breaks (including a final line break) remains material.
    canonical = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip(" \t") for line in canonical.split("\n"))


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _parse_json_value(value: Any) -> Any:
    if not isinstance(value, (str, bytes, bytearray)):
        _validate_json_value(value)
        return value
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", errors="strict")
    return json.loads(
        value,
        parse_constant=_reject_constant,
        object_pairs_hook=_object_without_duplicate_keys,
    )


def _validate_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string object key at {path}")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ValueError(f"non-JSON value at {path}")


def _json_values_equal(expected: Any, actual: Any) -> bool:
    # bool is a subclass of int in Python, although JSON booleans and numbers
    # are different value kinds.
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return expected == actual
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(
            _json_values_equal(expected[key], actual[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(
            _json_values_equal(left, right)
            for left, right in zip(expected, actual, strict=True)
        )
    return expected == actual


def compare_outputs(
    expected: Any,
    actual: Any,
    policy: ComparisonMode | str,
) -> ComparisonResult:
    """Compare two outputs and return the policy actually applied."""

    selected = ComparisonMode(policy)
    if selected is ComparisonMode.JSON_VALUE:
        try:
            normalized_expected = _parse_json_value(expected)
            normalized_actual = _parse_json_value(actual)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            return ComparisonResult(
                matched=False,
                policy=selected,
                normalized_expected=None,
                normalized_actual=None,
                error=f"invalid_json: {exc}",
            )
        return ComparisonResult(
            matched=_json_values_equal(normalized_expected, normalized_actual),
            policy=selected,
            normalized_expected=normalized_expected,
            normalized_actual=normalized_actual,
        )

    expected_text = _as_text(expected)
    actual_text = _as_text(actual)
    if selected is ComparisonMode.EXACT:
        normalized_expected, normalized_actual = expected_text, actual_text
    elif selected is ComparisonMode.IGNORE_FINAL_NEWLINE:
        normalized_expected = _remove_one_final_newline(expected_text)
        normalized_actual = _remove_one_final_newline(actual_text)
    elif selected is ComparisonMode.TRIM_TRAILING_WHITESPACE:
        normalized_expected = _trim_trailing_whitespace(expected_text)
        normalized_actual = _trim_trailing_whitespace(actual_text)
    elif selected is ComparisonMode.TOKEN_BASED:
        normalized_expected = expected_text.split()
        normalized_actual = actual_text.split()
    else:  # pragma: no cover - exhaustive through ComparisonMode
        raise AssertionError(f"unsupported comparison policy: {selected}")

    return ComparisonResult(
        matched=normalized_expected == normalized_actual,
        policy=selected,
        normalized_expected=normalized_expected,
        normalized_actual=normalized_actual,
    )
