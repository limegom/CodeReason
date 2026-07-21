from __future__ import annotations

import ast
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "20260714_0001_initial_schema.py"
)

EXPECTED_ENUMS = {
    "analysis_provenance": ("LIVE", "STORED_LIVE", "DEMO_FIXTURE", "UNAVAILABLE"),
    "analysis_status": ("PENDING", "RUNNING", "COMPLETED", "FAILED", "STALE"),
    "applied_comparison_mode": (
        "EXACT",
        "IGNORE_FINAL_NEWLINE",
        "TRIM_TRAILING_WHITESPACE",
        "TOKEN_BASED",
        "JSON_VALUE",
    ),
    "assignment_provenance": ("LIVE", "STORED_LIVE", "DEMO_FIXTURE", "UNAVAILABLE"),
    "comparison_mode": (
        "EXACT",
        "IGNORE_FINAL_NEWLINE",
        "TRIM_TRAILING_WHITESPACE",
        "TOKEN_BASED",
        "JSON_VALUE",
    ),
    "consistency_issue_severity": ("LOW", "MEDIUM", "HIGH"),
    "consistency_issue_status": ("OPEN", "DISMISSED", "RESOLVED"),
    "evidence_kind": (
        "TestResult",
        "ExecutionError",
        "ASTFinding",
        "StaticFinding",
        "SourceCodeLocation",
    ),
    "evidence_provenance": ("LIVE", "STORED_LIVE", "DEMO_FIXTURE", "UNAVAILABLE"),
    "evidence_visibility": ("INTERNAL", "REVIEWER_ONLY", "STUDENT_VISIBLE"),
    "execution_error_category": (
        "SYNTAX_ERROR",
        "RUNTIME_ERROR",
        "TIMEOUT",
        "WRONG_ANSWER",
        "SECURITY_VIOLATION",
        "EXECUTION_UNAVAILABLE",
        "INTERNAL_ERROR",
    ),
    "execution_mode": ("FUNCTION", "STDIN_STDOUT"),
    "execution_provenance": ("LIVE", "STORED_LIVE", "DEMO_FIXTURE", "UNAVAILABLE"),
    "execution_status": (
        "PENDING",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "TIMED_OUT",
        "UNAVAILABLE",
    ),
    "review_status": ("PENDING", "IN_REVIEW", "APPROVED", "CHANGES_REQUESTED"),
    "rubric_origin": ("HUMAN", "AI_STRUCTURED"),
    "rubric_parse_provenance": (
        "LIVE",
        "STORED_LIVE",
        "DEMO_FIXTURE",
        "UNAVAILABLE",
    ),
    "rubric_parse_status": ("PENDING", "RUNNING", "COMPLETED", "FAILED", "STALE"),
    "rubric_status": ("DRAFT", "AI_STRUCTURED", "HUMAN_APPROVED", "ARCHIVED"),
    "submission_provenance": ("LIVE", "STORED_LIVE", "DEMO_FIXTURE", "UNAVAILABLE"),
    "submission_status": (
        "UPLOADED",
        "QUEUED",
        "ANALYZING",
        "REVIEW_REQUIRED",
        "APPROVED",
        "FAILED",
    ),
    "test_comparison_mode": (
        "EXACT",
        "IGNORE_FINAL_NEWLINE",
        "TRIM_TRAILING_WHITESPACE",
        "TOKEN_BASED",
        "JSON_VALUE",
    ),
    "test_result_error_category": (
        "SYNTAX_ERROR",
        "RUNTIME_ERROR",
        "TIMEOUT",
        "WRONG_ANSWER",
        "SECURITY_VIOLATION",
        "EXECUTION_UNAVAILABLE",
        "INTERNAL_ERROR",
    ),
    "test_result_status": ("PASSED", "FAILED", "ERROR", "TIMED_OUT", "SKIPPED"),
}


def _enum_snapshot(migration: str) -> dict[str, tuple[str, ...]]:
    definitions: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(ast.parse(migration)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_enum"
        ):
            continue
        arguments = tuple(
            argument.value
            for argument in node.args
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        )
        assert len(arguments) == len(node.args)
        name, *values = arguments
        assert name not in definitions
        definitions[name] = tuple(values)
    return definitions


def test_initial_migration_is_a_frozen_schema_snapshot() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    forbidden_dynamic_schema_references = (
        "Base.metadata",
        "create_all",
        "drop_all",
        "from app",
        "import app.models",
    )
    for forbidden in forbidden_dynamic_schema_references:
        assert forbidden not in migration

    assert migration.count("op.create_table(") == 15
    assert migration.count("op.create_index(") == 20
    assert 'revision = "20260714_0001"' in migration
    assert "down_revision = None" in migration
    assert _enum_snapshot(migration) == EXPECTED_ENUMS
