from __future__ import annotations

from app.deterministic.ast_analysis import analyze_python_source


def _by_rule(report, rule):
    return [finding for finding in report.ast_findings if finding.rule == rule]


def test_ast_reports_observed_structure_and_signature_only():
    report = analyze_python_source(
        """\
def make_matrix(data, rows, cols):
    result = []
    for row in range(rows):
        if row < len(data):
            result.append(data[row * cols:(row + 1) * cols])
    return result
""",
        expected_function="make_matrix",
        expected_parameters=["data", "rows", "cols"],
    )

    assert report.syntax_error is None
    assert _by_rule(report, "expected_function_exists")[0].passed is True
    assert _by_rule(report, "signature_matches")[0].passed is True
    signature = _by_rule(report, "function_signature_observed")[0]
    assert signature.details["parameter_count"] == 3
    assert signature.details["parameter_names"] == ["data", "rows", "cols"]
    assert _by_rule(report, "loop_present")[0].passed is True
    assert _by_rule(report, "conditional_present")[0].passed is True
    assert all("understand" not in finding.message.lower() for finding in report.ast_findings)


def test_missing_function_and_syntax_error_are_distinct_observations():
    missing = analyze_python_source("value = 3\n", expected_function="solve")
    invalid = analyze_python_source("def solve(:\n    pass\n", expected_function="solve")

    assert _by_rule(missing, "expected_function_exists")[0].passed is False
    assert invalid.syntax_error is not None
    assert invalid.syntax_error.category == "SYNTAX_ERROR"


def test_restricted_calls_and_literals_are_conservative_static_findings():
    report = analyze_python_source(
        """\
import os
DATA = [1, 2, 3, 4]
def solve():
    os.system('echo no')
    return 'answers.json'
""",
        expected_function="solve",
    )

    restricted = [
        finding for finding in report.static_findings if finding.rule == "restricted_api_reference"
    ]
    candidates = [
        finding for finding in report.static_findings if finding.rule == "hardcoded_literal_candidate"
    ]
    assert restricted and restricted[0].details["call"] == "os.system"
    assert candidates
    assert "does not establish intent" in candidates[0].message


def test_literal_matrix_return_is_only_a_hardcoding_candidate():
    report = analyze_python_source(
        "def solve(data):\n    return [[1, 2], [3, 4]]\n",
        expected_function="solve",
    )

    candidates = [
        finding for finding in report.static_findings if finding.rule == "hardcoded_literal_candidate"
    ]
    assert candidates
    assert all("intent" in finding.message for finding in candidates)
