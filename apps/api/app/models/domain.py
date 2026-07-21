from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    AnalysisStatus,
    ComparisonMode,
    DataProvenance,
    ConsistencyIssueSeverity,
    ConsistencyIssueStatus,
    ErrorCategory,
    EvidenceKind,
    EvidenceVisibility,
    ExecutionMode,
    ExecutionStatus,
    ReviewStatus,
    RubricOrigin,
    RubricStatus,
    SubmissionStatus,
    TestResultStatus,
)


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_type(enum_class: type, name: str) -> Enum:
    return Enum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
        validate_strings=True,
        create_constraint=True,
    )


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Assignment(IdMixin, TimestampMixin, Base):
    __tablename__ = "assignments"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    demo_key: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    total_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("20"), nullable=False
    )
    time_limit_ms: Mapped[int] = mapped_column(Integer, default=2_000, nullable=False)
    python_version: Mapped[str] = mapped_column(String(20), default="3.12", nullable=False)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        enum_type(ExecutionMode, "execution_mode"), nullable=False
    )
    entry_function: Mapped[str | None] = mapped_column(String(128))
    arguments_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    comparison_mode: Mapped[ComparisonMode] = mapped_column(
        enum_type(ComparisonMode, "comparison_mode"), default=ComparisonMode.EXACT, nullable=False
    )
    analysis_input_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    provenance: Mapped[DataProvenance] = mapped_column(
        enum_type(DataProvenance, "assignment_provenance"),
        default=DataProvenance.LIVE,
        nullable=False,
    )

    rubric_criteria: Mapped[list[RubricCriterion]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", order_by="RubricCriterion.sort_order"
    )
    rubric_parse_jobs: Mapped[list[RubricParseJob]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )
    test_cases: Mapped[list[TestCase]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", order_by="TestCase.sort_order"
    )
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )


class RubricCriterion(IdMixin, TimestampMixin, Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (UniqueConstraint("assignment_id", "criterion_key", name="uq_rubric_assignment_key"),)

    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    criterion_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    origin: Mapped[RubricOrigin] = mapped_column(
        enum_type(RubricOrigin, "rubric_origin"), default=RubricOrigin.HUMAN, nullable=False
    )
    approval_status: Mapped[RubricStatus] = mapped_column(
        enum_type(RubricStatus, "rubric_status"), default=RubricStatus.DRAFT, nullable=False
    )
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    assignment: Mapped[Assignment] = relationship(back_populates="rubric_criteria")
    derived_scores: Mapped[list[RubricScore]] = relationship(back_populates="rubric_criterion")
    human_scores: Mapped[list[HumanRubricScore]] = relationship(back_populates="rubric_criterion")


class RubricParseJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "rubric_parse_jobs"

    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        enum_type(AnalysisStatus, "rubric_parse_status"),
        default=AnalysisStatus.PENDING,
        nullable=False,
    )
    policy_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="openai", nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(String(255))
    input_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    sanitized_input_hash: Mapped[str | None] = mapped_column(String(64))
    external_data_manifest: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    uncertainties: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[DataProvenance] = mapped_column(
        enum_type(DataProvenance, "rubric_parse_provenance"),
        default=DataProvenance.LIVE,
        nullable=False,
    )

    assignment: Mapped[Assignment] = relationship(back_populates="rubric_parse_jobs")


class TestCase(IdMixin, TimestampMixin, Base):
    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("assignment_id", "name", name="uq_test_case_assignment_name"),)

    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    input_payload: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    expected_output: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    comparison_mode: Mapped[ComparisonMode | None] = mapped_column(
        enum_type(ComparisonMode, "test_comparison_mode")
    )
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    assignment: Mapped[Assignment] = relationship(back_populates="test_cases")
    results: Mapped[list[TestResult]] = relationship(back_populates="test_case")


class Submission(IdMixin, TimestampMixin, Base):
    __tablename__ = "submissions"

    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    student_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        enum_type(SubmissionStatus, "submission_status"), default=SubmissionStatus.UPLOADED, nullable=False
    )
    source_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provenance: Mapped[DataProvenance] = mapped_column(
        enum_type(DataProvenance, "submission_provenance"),
        default=DataProvenance.LIVE,
        nullable=False,
    )

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    source_files: Mapped[list[SourceFile]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="SourceFile.revision"
    )
    execution_runs: Mapped[list[ExecutionRun]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    analyses: Mapped[list[AIAnalysis]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    human_reviews: Mapped[list[HumanReview]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class SourceFile(IdMixin, TimestampMixin, Base):
    __tablename__ = "source_files"
    __table_args__ = (
        UniqueConstraint("submission_id", "revision", "filename", name="uq_source_submission_revision_file"),
    )

    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    submission: Mapped[Submission] = relationship(back_populates="source_files")
    evidence_locations: Mapped[list[Evidence]] = relationship(back_populates="source_file")


class ExecutionRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "execution_runs"

    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    status: Mapped[ExecutionStatus] = mapped_column(
        enum_type(ExecutionStatus, "execution_status"), default=ExecutionStatus.PENDING, nullable=False
    )
    runner_version: Mapped[str] = mapped_column(String(100), nullable=False)
    image_digest: Mapped[str | None] = mapped_column(String(255))
    error_category: Mapped[ErrorCategory | None] = mapped_column(
        enum_type(ErrorCategory, "execution_error_category")
    )
    exception_type: Mapped[str | None] = mapped_column(String(255))
    signature_status: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    assignment_input_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provenance: Mapped[DataProvenance] = mapped_column(
        enum_type(DataProvenance, "execution_provenance"),
        default=DataProvenance.LIVE,
        nullable=False,
    )

    submission: Mapped[Submission] = relationship(back_populates="execution_runs")
    test_results: Mapped[list[TestResult]] = relationship(
        back_populates="execution_run", cascade="all, delete-orphan"
    )
    evidence: Mapped[list[Evidence]] = relationship(back_populates="execution_run")


class TestResult(IdMixin, TimestampMixin, Base):
    __tablename__ = "test_results"
    __table_args__ = (UniqueConstraint("execution_run_id", "test_case_id", name="uq_run_test_case"),)

    execution_run_id: Mapped[str] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="CASCADE"), index=True
    )
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="RESTRICT"), index=True)
    status: Mapped[TestResultStatus] = mapped_column(
        enum_type(TestResultStatus, "test_result_status"), nullable=False
    )
    applied_comparison_mode: Mapped[ComparisonMode] = mapped_column(
        enum_type(ComparisonMode, "applied_comparison_mode"), nullable=False
    )
    actual_output: Mapped[str | None] = mapped_column(Text)
    stderr: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    error_category: Mapped[ErrorCategory | None] = mapped_column(
        enum_type(ErrorCategory, "test_result_error_category")
    )
    duration_ms: Mapped[float | None] = mapped_column(Float)
    result_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    execution_run: Mapped[ExecutionRun] = relationship(back_populates="test_results")
    test_case: Mapped[TestCase] = relationship(back_populates="results")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="test_result")


rubric_score_evidence = Table(
    "rubric_score_evidence",
    Base.metadata,
    Column("rubric_score_id", ForeignKey("rubric_scores.id", ondelete="CASCADE"), primary_key=True),
    Column("evidence_id", ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True),
)


class Evidence(IdMixin, TimestampMixin, Base):
    __tablename__ = "evidence"

    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    execution_run_id: Mapped[str | None] = mapped_column(ForeignKey("execution_runs.id", ondelete="SET NULL"))
    test_result_id: Mapped[str | None] = mapped_column(ForeignKey("test_results.id", ondelete="SET NULL"))
    source_file_id: Mapped[str | None] = mapped_column(ForeignKey("source_files.id", ondelete="SET NULL"))
    kind: Mapped[EvidenceKind] = mapped_column(enum_type(EvidenceKind, "evidence_kind"), nullable=False)
    visibility: Mapped[EvidenceVisibility] = mapped_column(
        enum_type(EvidenceVisibility, "evidence_visibility"),
        default=EvidenceVisibility.REVIEWER_ONLY,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    provenance: Mapped[DataProvenance] = mapped_column(
        enum_type(DataProvenance, "evidence_provenance"),
        default=DataProvenance.LIVE,
        nullable=False,
    )

    submission: Mapped[Submission] = relationship(back_populates="evidence")
    execution_run: Mapped[ExecutionRun | None] = relationship(back_populates="evidence")
    test_result: Mapped[TestResult | None] = relationship(back_populates="evidence")
    source_file: Mapped[SourceFile | None] = relationship(back_populates="evidence_locations")
    derived_scores: Mapped[list[RubricScore]] = relationship(
        secondary=rubric_score_evidence, back_populates="primary_evidence"
    )


class AIAnalysis(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_analyses"

    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    execution_run_id: Mapped[str | None] = mapped_column(ForeignKey("execution_runs.id", ondelete="SET NULL"))
    status: Mapped[AnalysisStatus] = mapped_column(
        enum_type(AnalysisStatus, "analysis_status"), default=AnalysisStatus.PENDING, nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="unknown", nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text)
    model_reported_confidence: Mapped[float | None] = mapped_column(Float)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    assignment_input_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sanitized_input_hash: Mapped[str | None] = mapped_column(String(64))
    external_data_manifest: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[DataProvenance] = mapped_column(
        enum_type(DataProvenance, "analysis_provenance"),
        default=DataProvenance.LIVE,
        nullable=False,
    )

    submission: Mapped[Submission] = relationship(back_populates="analyses")
    rubric_scores: Mapped[list[RubricScore]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    human_reviews: Mapped[list[HumanReview]] = relationship(back_populates="ai_analysis")


class RubricScore(IdMixin, TimestampMixin, Base):
    __tablename__ = "rubric_scores"
    __table_args__ = (
        UniqueConstraint("analysis_id", "rubric_criterion_id", name="uq_analysis_rubric_score"),
    )

    analysis_id: Mapped[str] = mapped_column(ForeignKey("ai_analyses.id", ondelete="CASCADE"), index=True)
    rubric_criterion_id: Mapped[str] = mapped_column(
        ForeignKey("rubric_criteria.id", ondelete="RESTRICT"), index=True
    )
    suggested_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    interpretation: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text)
    model_reported_confidence: Mapped[float | None] = mapped_column(Float)

    analysis: Mapped[AIAnalysis] = relationship(back_populates="rubric_scores")
    rubric_criterion: Mapped[RubricCriterion] = relationship(back_populates="derived_scores")
    primary_evidence: Mapped[list[Evidence]] = relationship(
        secondary=rubric_score_evidence, back_populates="derived_scores"
    )


class HumanReview(IdMixin, TimestampMixin, Base):
    __tablename__ = "human_reviews"

    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    ai_analysis_id: Mapped[str | None] = mapped_column(ForeignKey("ai_analyses.id", ondelete="SET NULL"))
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        enum_type(ReviewStatus, "review_status"), default=ReviewStatus.PENDING, nullable=False
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_assignment_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="human_reviews")
    ai_analysis: Mapped[AIAnalysis | None] = relationship(back_populates="human_reviews")
    scores: Mapped[list[HumanRubricScore]] = relationship(
        back_populates="human_review", cascade="all, delete-orphan"
    )


class HumanRubricScore(IdMixin, TimestampMixin, Base):
    __tablename__ = "human_rubric_scores"
    __table_args__ = (
        UniqueConstraint("human_review_id", "rubric_criterion_id", name="uq_review_rubric_score"),
    )

    human_review_id: Mapped[str] = mapped_column(ForeignKey("human_reviews.id", ondelete="CASCADE"), index=True)
    rubric_criterion_id: Mapped[str] = mapped_column(
        ForeignKey("rubric_criteria.id", ondelete="RESTRICT"), index=True
    )
    awarded_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    human_review: Mapped[HumanReview] = relationship(back_populates="scores")
    rubric_criterion: Mapped[RubricCriterion] = relationship(back_populates="human_scores")


class ConsistencyIssue(IdMixin, TimestampMixin, Base):
    __tablename__ = "consistency_issues"

    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    compared_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL")
    )
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("ai_analyses.id", ondelete="SET NULL"))
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[ConsistencyIssueSeverity] = mapped_column(
        enum_type(ConsistencyIssueSeverity, "consistency_issue_severity"),
        default=ConsistencyIssueSeverity.LOW,
        nullable=False,
    )
    status: Mapped[ConsistencyIssueStatus] = mapped_column(
        enum_type(ConsistencyIssueStatus, "consistency_issue_status"),
        default=ConsistencyIssueStatus.OPEN,
        nullable=False,
    )
    potential_issue: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    test_status_vector: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(100))
    ast_feature_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    exception_type: Mapped[str | None] = mapped_column(String(255))
    signature_status: Mapped[str | None] = mapped_column(String(100))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(200))
