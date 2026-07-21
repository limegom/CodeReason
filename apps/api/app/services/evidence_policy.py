from __future__ import annotations

from typing import Any

from app.models import Evidence, EvidenceVisibility, TestCase


HIDDEN_TEST_MESSAGE = "A hidden test produced evidence; its input and expected answer are withheld."


def test_case_for_student(test_case: TestCase) -> dict[str, Any]:
    if test_case.is_hidden:
        return {
            "id": test_case.id,
            "name": test_case.name,
            "is_hidden": True,
            "comparison_mode": test_case.comparison_mode,
            "input_payload": None,
            "expected_output": None,
        }
    return {
        "id": test_case.id,
        "name": test_case.name,
        "is_hidden": False,
        "comparison_mode": test_case.comparison_mode,
        "input_payload": test_case.input_payload,
        "expected_output": test_case.expected_output,
    }


def evidence_for_student(evidence: Evidence) -> dict[str, Any] | None:
    if evidence.visibility != EvidenceVisibility.STUDENT_VISIBLE:
        return None

    hidden_test = evidence.test_result is not None and evidence.test_result.test_case.is_hidden
    if hidden_test:
        details = {
            "status": evidence.test_result.status,
            "error_category": evidence.test_result.error_category,
            "comparison_mode": evidence.test_result.applied_comparison_mode,
        }
        summary = HIDDEN_TEST_MESSAGE
    else:
        details = evidence.details
        summary = evidence.summary
    return {
        "id": evidence.id,
        "kind": evidence.kind,
        "visibility": evidence.visibility,
        "summary": summary,
        "details": details,
        "source_file_id": evidence.source_file_id,
        "start_line": evidence.start_line,
        "end_line": evidence.end_line,
    }


def evidence_for_external_ai(evidence: Evidence) -> dict[str, Any] | None:
    """Return the minimum inspectable record allowed to leave the service.

    INTERNAL evidence never leaves the service. Hidden tests disclose only the
    outcome category and applied comparison policy; input, expected output,
    actual output, stderr, and free-form details are deliberately omitted.
    """

    if evidence.visibility == EvidenceVisibility.INTERNAL:
        return None

    projected: dict[str, Any] = {
        "id": evidence.id,
        "kind": evidence.kind.value,
        "visibility": evidence.visibility.value,
        "summary": evidence.summary,
        "source_location": (
            {
                "start_line": evidence.start_line,
                "end_line": evidence.end_line,
            }
            if evidence.start_line is not None
            else None
        ),
    }
    if evidence.test_result is None:
        projected["details"] = evidence.details
        return projected

    result = evidence.test_result
    hidden = result.test_case.is_hidden
    projected["summary"] = HIDDEN_TEST_MESSAGE if hidden else evidence.summary
    projected["test_observation"] = {
        "status": result.status.value,
        "error_category": result.error_category.value if result.error_category else None,
        "comparison_mode": result.applied_comparison_mode.value,
        "duration_ms": result.duration_ms,
        "actual_output": None if hidden else result.actual_output,
        "stderr": None if hidden else result.stderr,
        "exit_code": None if hidden else result.exit_code,
        "hidden_values_withheld": hidden,
    }
    return projected
