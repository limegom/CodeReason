"""Initial schema.

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260714_0001"
down_revision = None
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def _identity_columns() -> tuple[sa.Column, sa.Column, sa.Column]:
    return (
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("demo_key", sa.String(length=80), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("total_score", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("time_limit_ms", sa.Integer(), nullable=False),
        sa.Column("python_version", sa.String(length=20), nullable=False),
        sa.Column(
            "execution_mode",
            _enum("execution_mode", "FUNCTION", "STDIN_STDOUT"),
            nullable=False,
        ),
        sa.Column("entry_function", sa.String(length=128), nullable=True),
        sa.Column("arguments_schema", sa.JSON(), nullable=False),
        sa.Column(
            "comparison_mode",
            _enum(
                "comparison_mode",
                "EXACT",
                "IGNORE_FINAL_NEWLINE",
                "TRIM_TRAILING_WHITESPACE",
                "TOKEN_BASED",
                "JSON_VALUE",
            ),
            nullable=False,
        ),
        sa.Column("analysis_input_version", sa.Integer(), nullable=False),
        sa.Column(
            "provenance",
            _enum(
                "assignment_provenance",
                "LIVE",
                "STORED_LIVE",
                "DEMO_FIXTURE",
                "UNAVAILABLE",
            ),
            nullable=False,
        ),
        *_identity_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assignments_demo_key",
        "assignments",
        ["demo_key"],
        unique=True,
    )

    op.create_table(
        "rubric_criteria",
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("criterion_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("max_score", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "origin",
            _enum("rubric_origin", "HUMAN", "AI_STRUCTURED"),
            nullable=False,
        ),
        sa.Column(
            "approval_status",
            _enum(
                "rubric_status",
                "DRAFT",
                "AI_STRUCTURED",
                "HUMAN_APPROVED",
                "ARCHIVED",
            ),
            nullable=False,
        ),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assignment_id",
            "criterion_key",
            name="uq_rubric_assignment_key",
        ),
    )
    op.create_index(
        "ix_rubric_criteria_assignment_id",
        "rubric_criteria",
        ["assignment_id"],
    )

    op.create_table(
        "rubric_parse_jobs",
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            _enum(
                "rubric_parse_status",
                "PENDING",
                "RUNNING",
                "COMPLETED",
                "FAILED",
                "STALE",
            ),
            nullable=False,
        ),
        sa.Column("policy_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("provider_response_id", sa.String(length=255), nullable=True),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("sanitized_input_hash", sa.String(length=64), nullable=True),
        sa.Column("external_data_manifest", sa.JSON(), nullable=False),
        sa.Column("uncertainties", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provenance",
            _enum(
                "rubric_parse_provenance",
                "LIVE",
                "STORED_LIVE",
                "DEMO_FIXTURE",
                "UNAVAILABLE",
            ),
            nullable=False,
        ),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rubric_parse_jobs_assignment_id",
        "rubric_parse_jobs",
        ["assignment_id"],
    )

    op.create_table(
        "submissions",
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("student_reference", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            _enum(
                "submission_status",
                "UPLOADED",
                "QUEUED",
                "ANALYZING",
                "REVIEW_REQUIRED",
                "APPROVED",
                "FAILED",
            ),
            nullable=False,
        ),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column(
            "provenance",
            _enum(
                "submission_provenance",
                "LIVE",
                "STORED_LIVE",
                "DEMO_FIXTURE",
                "UNAVAILABLE",
            ),
            nullable=False,
        ),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_submissions_assignment_id",
        "submissions",
        ["assignment_id"],
    )

    op.create_table(
        "test_cases",
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("expected_output", sa.JSON(), nullable=True),
        sa.Column(
            "comparison_mode",
            _enum(
                "test_comparison_mode",
                "EXACT",
                "IGNORE_FINAL_NEWLINE",
                "TRIM_TRAILING_WHITESPACE",
                "TOKEN_BASED",
                "JSON_VALUE",
            ),
            nullable=True,
        ),
        sa.Column("is_hidden", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assignment_id",
            "name",
            name="uq_test_case_assignment_name",
        ),
    )
    op.create_index(
        "ix_test_cases_assignment_id",
        "test_cases",
        ["assignment_id"],
    )

    op.create_table(
        "execution_runs",
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            _enum(
                "execution_status",
                "PENDING",
                "RUNNING",
                "COMPLETED",
                "FAILED",
                "TIMED_OUT",
                "UNAVAILABLE",
            ),
            nullable=False,
        ),
        sa.Column("runner_version", sa.String(length=100), nullable=False),
        sa.Column("image_digest", sa.String(length=255), nullable=True),
        sa.Column(
            "error_category",
            _enum(
                "execution_error_category",
                "SYNTAX_ERROR",
                "RUNTIME_ERROR",
                "TIMEOUT",
                "WRONG_ANSWER",
                "SECURITY_VIOLATION",
                "EXECUTION_UNAVAILABLE",
                "INTERNAL_ERROR",
            ),
            nullable=True,
        ),
        sa.Column("exception_type", sa.String(length=255), nullable=True),
        sa.Column("signature_status", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_metadata", sa.JSON(), nullable=False),
        sa.Column("assignment_input_version", sa.Integer(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column(
            "provenance",
            _enum(
                "execution_provenance",
                "LIVE",
                "STORED_LIVE",
                "DEMO_FIXTURE",
                "UNAVAILABLE",
            ),
            nullable=False,
        ),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_execution_runs_submission_id",
        "execution_runs",
        ["submission_id"],
    )

    op.create_table(
        "source_files",
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id",
            "revision",
            "filename",
            name="uq_source_submission_revision_file",
        ),
    )
    op.create_index(
        "ix_source_files_submission_id",
        "source_files",
        ["submission_id"],
    )

    op.create_table(
        "ai_analyses",
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("execution_run_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            _enum(
                "analysis_status",
                "PENDING",
                "RUNNING",
                "COMPLETED",
                "FAILED",
                "STALE",
            ),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("provider_response_id", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("model_reported_confidence", sa.Float(), nullable=True),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("assignment_input_version", sa.Integer(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("sanitized_input_hash", sa.String(length=64), nullable=True),
        sa.Column("external_data_manifest", sa.JSON(), nullable=False),
        sa.Column("token_usage", sa.JSON(), nullable=False),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provenance",
            _enum(
                "analysis_provenance",
                "LIVE",
                "STORED_LIVE",
                "DEMO_FIXTURE",
                "UNAVAILABLE",
            ),
            nullable=False,
        ),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["execution_run_id"],
            ["execution_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_analyses_submission_id",
        "ai_analyses",
        ["submission_id"],
    )

    op.create_table(
        "test_results",
        sa.Column("execution_run_id", sa.String(length=36), nullable=False),
        sa.Column("test_case_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            _enum(
                "test_result_status",
                "PASSED",
                "FAILED",
                "ERROR",
                "TIMED_OUT",
                "SKIPPED",
            ),
            nullable=False,
        ),
        sa.Column(
            "applied_comparison_mode",
            _enum(
                "applied_comparison_mode",
                "EXACT",
                "IGNORE_FINAL_NEWLINE",
                "TRIM_TRAILING_WHITESPACE",
                "TOKEN_BASED",
                "JSON_VALUE",
            ),
            nullable=False,
        ),
        sa.Column("actual_output", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column(
            "error_category",
            _enum(
                "test_result_error_category",
                "SYNTAX_ERROR",
                "RUNTIME_ERROR",
                "TIMEOUT",
                "WRONG_ANSWER",
                "SECURITY_VIOLATION",
                "EXECUTION_UNAVAILABLE",
                "INTERNAL_ERROR",
            ),
            nullable=True,
        ),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("result_metadata", sa.JSON(), nullable=False),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["execution_run_id"],
            ["execution_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_case_id"],
            ["test_cases.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_run_id",
            "test_case_id",
            name="uq_run_test_case",
        ),
    )
    op.create_index(
        "ix_test_results_execution_run_id",
        "test_results",
        ["execution_run_id"],
    )
    op.create_index(
        "ix_test_results_test_case_id",
        "test_results",
        ["test_case_id"],
    )

    op.create_table(
        "consistency_issues",
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("compared_submission_id", sa.String(length=36), nullable=True),
        sa.Column("analysis_id", sa.String(length=36), nullable=True),
        sa.Column("issue_type", sa.String(length=100), nullable=False),
        sa.Column(
            "severity",
            _enum("consistency_issue_severity", "LOW", "MEDIUM", "HIGH"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum(
                "consistency_issue_status",
                "OPEN",
                "DISMISSED",
                "RESOLVED",
            ),
            nullable=False,
        ),
        sa.Column("potential_issue", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=128), nullable=False),
        sa.Column("test_status_vector", sa.JSON(), nullable=False),
        sa.Column("error_category", sa.String(length=100), nullable=True),
        sa.Column("ast_feature_summary", sa.JSON(), nullable=False),
        sa.Column("exception_type", sa.String(length=255), nullable=True),
        sa.Column("signature_status", sa.String(length=100), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(length=200), nullable=True),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["ai_analyses.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["compared_submission_id"],
            ["submissions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_consistency_issues_assignment_id",
        "consistency_issues",
        ["assignment_id"],
    )
    op.create_index(
        "ix_consistency_issues_fingerprint_hash",
        "consistency_issues",
        ["fingerprint_hash"],
    )
    op.create_index(
        "ix_consistency_issues_submission_id",
        "consistency_issues",
        ["submission_id"],
    )

    op.create_table(
        "evidence",
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("execution_run_id", sa.String(length=36), nullable=True),
        sa.Column("test_result_id", sa.String(length=36), nullable=True),
        sa.Column("source_file_id", sa.String(length=36), nullable=True),
        sa.Column(
            "kind",
            _enum(
                "evidence_kind",
                "TestResult",
                "ExecutionError",
                "ASTFinding",
                "StaticFinding",
                "SourceCodeLocation",
            ),
            nullable=False,
        ),
        sa.Column(
            "visibility",
            _enum(
                "evidence_visibility",
                "INTERNAL",
                "REVIEWER_ONLY",
                "STUDENT_VISIBLE",
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("fingerprint", sa.String(length=128), nullable=True),
        sa.Column(
            "provenance",
            _enum(
                "evidence_provenance",
                "LIVE",
                "STORED_LIVE",
                "DEMO_FIXTURE",
                "UNAVAILABLE",
            ),
            nullable=False,
        ),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["execution_run_id"],
            ["execution_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["source_files.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_result_id"],
            ["test_results.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_fingerprint",
        "evidence",
        ["fingerprint"],
    )
    op.create_index(
        "ix_evidence_submission_id",
        "evidence",
        ["submission_id"],
    )

    op.create_table(
        "human_reviews",
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("ai_analysis_id", sa.String(length=36), nullable=True),
        sa.Column("reviewer", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            _enum(
                "review_status",
                "PENDING",
                "IN_REVIEW",
                "APPROVED",
                "CHANGES_REQUESTED",
            ),
            nullable=False,
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_assignment_version", sa.Integer(), nullable=False),
        sa.Column("reviewed_source_version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["ai_analysis_id"],
            ["ai_analyses.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_human_reviews_submission_id",
        "human_reviews",
        ["submission_id"],
    )

    op.create_table(
        "rubric_scores",
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("rubric_criterion_id", sa.String(length=36), nullable=False),
        sa.Column(
            "suggested_score",
            sa.Numeric(precision=8, scale=2),
            nullable=False,
        ),
        sa.Column("interpretation", sa.Text(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("model_reported_confidence", sa.Float(), nullable=True),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["ai_analyses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_criterion_id"],
            ["rubric_criteria.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id",
            "rubric_criterion_id",
            name="uq_analysis_rubric_score",
        ),
    )
    op.create_index(
        "ix_rubric_scores_analysis_id",
        "rubric_scores",
        ["analysis_id"],
    )
    op.create_index(
        "ix_rubric_scores_rubric_criterion_id",
        "rubric_scores",
        ["rubric_criterion_id"],
    )

    op.create_table(
        "human_rubric_scores",
        sa.Column("human_review_id", sa.String(length=36), nullable=False),
        sa.Column("rubric_criterion_id", sa.String(length=36), nullable=False),
        sa.Column(
            "awarded_score",
            sa.Numeric(precision=8, scale=2),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        *_identity_columns(),
        sa.ForeignKeyConstraint(
            ["human_review_id"],
            ["human_reviews.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_criterion_id"],
            ["rubric_criteria.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "human_review_id",
            "rubric_criterion_id",
            name="uq_review_rubric_score",
        ),
    )
    op.create_index(
        "ix_human_rubric_scores_human_review_id",
        "human_rubric_scores",
        ["human_review_id"],
    )
    op.create_index(
        "ix_human_rubric_scores_rubric_criterion_id",
        "human_rubric_scores",
        ["rubric_criterion_id"],
    )

    op.create_table(
        "rubric_score_evidence",
        sa.Column("rubric_score_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_score_id"],
            ["rubric_scores.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("rubric_score_id", "evidence_id"),
    )


def downgrade() -> None:
    op.drop_table("rubric_score_evidence")
    op.drop_index(
        "ix_human_rubric_scores_rubric_criterion_id",
        table_name="human_rubric_scores",
    )
    op.drop_index(
        "ix_human_rubric_scores_human_review_id",
        table_name="human_rubric_scores",
    )
    op.drop_table("human_rubric_scores")
    op.drop_index(
        "ix_rubric_scores_rubric_criterion_id",
        table_name="rubric_scores",
    )
    op.drop_index(
        "ix_rubric_scores_analysis_id",
        table_name="rubric_scores",
    )
    op.drop_table("rubric_scores")
    op.drop_index(
        "ix_human_reviews_submission_id",
        table_name="human_reviews",
    )
    op.drop_table("human_reviews")
    op.drop_index("ix_evidence_submission_id", table_name="evidence")
    op.drop_index("ix_evidence_fingerprint", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index(
        "ix_consistency_issues_submission_id",
        table_name="consistency_issues",
    )
    op.drop_index(
        "ix_consistency_issues_fingerprint_hash",
        table_name="consistency_issues",
    )
    op.drop_index(
        "ix_consistency_issues_assignment_id",
        table_name="consistency_issues",
    )
    op.drop_table("consistency_issues")
    op.drop_index(
        "ix_test_results_test_case_id",
        table_name="test_results",
    )
    op.drop_index(
        "ix_test_results_execution_run_id",
        table_name="test_results",
    )
    op.drop_table("test_results")
    op.drop_index(
        "ix_ai_analyses_submission_id",
        table_name="ai_analyses",
    )
    op.drop_table("ai_analyses")
    op.drop_index(
        "ix_source_files_submission_id",
        table_name="source_files",
    )
    op.drop_table("source_files")
    op.drop_index(
        "ix_execution_runs_submission_id",
        table_name="execution_runs",
    )
    op.drop_table("execution_runs")
    op.drop_index(
        "ix_test_cases_assignment_id",
        table_name="test_cases",
    )
    op.drop_table("test_cases")
    op.drop_index(
        "ix_submissions_assignment_id",
        table_name="submissions",
    )
    op.drop_table("submissions")
    op.drop_index(
        "ix_rubric_parse_jobs_assignment_id",
        table_name="rubric_parse_jobs",
    )
    op.drop_table("rubric_parse_jobs")
    op.drop_index(
        "ix_rubric_criteria_assignment_id",
        table_name="rubric_criteria",
    )
    op.drop_table("rubric_criteria")
    op.drop_index("ix_assignments_demo_key", table_name="assignments")
    op.drop_table("assignments")
