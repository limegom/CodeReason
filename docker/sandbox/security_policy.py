"""Validation constants used inside the sandbox image."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SOURCE_PATH = Path("/input/submission.py")
MAX_SOURCE_BYTES = 256 * 1024
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_TESTS = 100
MIN_TIMEOUT_MS = 50
MAX_TIMEOUT_MS = 5_000
MIN_OUTPUT_BYTES = 1_024
MAX_OUTPUT_BYTES = 65_536
MAX_STDIN_BYTES = 256 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$", flags=re.ASCII)
_COMPARISON_MODES = {
    "EXACT",
    "IGNORE_FINAL_NEWLINE",
    "TRIM_TRAILING_WHITESPACE",
    "TOKEN_BASED",
    "JSON_VALUE",
}


class InvalidRunnerRequest(ValueError):
    pass


def read_json_object(path: Path, max_bytes: int) -> dict[str, Any]:
    if path.stat().st_size > max_bytes:
        raise InvalidRunnerRequest("request exceeds size limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InvalidRunnerRequest("request must be an object")
    return value


def read_json_bytes(value: bytes, max_bytes: int) -> dict[str, Any]:
    if len(value) > max_bytes:
        raise InvalidRunnerRequest("request exceeds size limit")
    parsed = json.loads(value.decode("utf-8", errors="strict"))
    if not isinstance(parsed, dict):
        raise InvalidRunnerRequest("request must be an object")
    return parsed


def validate_request(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") != 1:
        raise InvalidRunnerRequest("unsupported runner request version")
    execution = payload.get("execution")
    limits = payload.get("limits")
    tests = payload.get("tests")
    if not isinstance(execution, dict) or not isinstance(limits, dict):
        raise InvalidRunnerRequest("execution and limits objects are required")
    if not isinstance(tests, list) or not 1 <= len(tests) <= MAX_TESTS:
        raise InvalidRunnerRequest("invalid number of test cases")

    mode = execution.get("mode")
    entry_function = execution.get("entry_function")
    if mode not in {"FUNCTION", "STDIN_STDOUT"}:
        raise InvalidRunnerRequest("invalid execution mode")
    if mode == "FUNCTION" and (
        not isinstance(entry_function, str) or not _IDENTIFIER.fullmatch(entry_function)
    ):
        raise InvalidRunnerRequest("FUNCTION mode requires an entry function")
    if mode == "STDIN_STDOUT" and entry_function is not None:
        raise InvalidRunnerRequest("STDIN_STDOUT cannot define an entry function")

    timeout_ms = limits.get("per_test_timeout_ms")
    output_bytes = limits.get("max_output_bytes")
    if not isinstance(timeout_ms, int) or not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS:
        raise InvalidRunnerRequest("invalid per-test timeout")
    if not isinstance(output_bytes, int) or not MIN_OUTPUT_BYTES <= output_bytes <= MAX_OUTPUT_BYTES:
        raise InvalidRunnerRequest("invalid output limit")

    seen: set[str] = set()
    for test in tests:
        if not isinstance(test, dict):
            raise InvalidRunnerRequest("test case must be an object")
        test_id = test.get("test_case_id")
        if not isinstance(test_id, str) or not test_id or test_id in seen:
            raise InvalidRunnerRequest("invalid or duplicate test_case_id")
        seen.add(test_id)
        if test.get("comparison_mode") not in _COMPARISON_MODES:
            raise InvalidRunnerRequest("invalid comparison mode")
        test_input = test.get("input")
        if mode == "STDIN_STDOUT":
            if not isinstance(test_input, str):
                raise InvalidRunnerRequest("stdin input must be text")
            if len(test_input.encode("utf-8")) > MAX_STDIN_BYTES:
                raise InvalidRunnerRequest("stdin input exceeds size limit")
        else:
            if not isinstance(test_input, dict):
                raise InvalidRunnerRequest("function input must be an object")
            if not isinstance(test_input.get("args"), list) or not isinstance(
                test_input.get("kwargs"), dict
            ):
                raise InvalidRunnerRequest("function input requires args and kwargs")

    if SOURCE_PATH.stat().st_size > MAX_SOURCE_BYTES:
        raise InvalidRunnerRequest("source exceeds size limit")
    return payload


def safe_error_message(value: object, limit: int = 500) -> str:
    text = " ".join(str(value).split())
    return text[:limit]
