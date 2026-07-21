from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AssignmentFields(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    total_score: Decimal = Field(default=Decimal("20"), gt=0)
    time_limit_ms: int = Field(default=2_000, ge=50, le=5_000)
    python_version: str = Field(default="3.12", pattern=r"^3\.12(?:\.\d+)?$")
    execution_mode: ExecutionMode
    entry_function: str | None = Field(default=None, max_length=128)
    arguments_schema: dict[str, Any] = Field(default_factory=dict)
    comparison_mode: ComparisonMode = ComparisonMode.EXACT

    @field_validator("title", "entry_function")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_execution_contract(self) -> AssignmentFields:
        if self.execution_mode == ExecutionMode.FUNCTION and not self.entry_function:
            raise ValueError("entry_function is required when execution_mode is FUNCTION")
        if self.execution_mode == ExecutionMode.STDIN_STDOUT and self.entry_function is not None:
            raise ValueError("entry_function must be omitted when execution_mode is STDIN_STDOUT")
        if self.execution_mode == ExecutionMode.FUNCTION:
            schema_type = self.arguments_schema.get("type")
            if schema_type is not None and schema_type not in {"array", "object"}:
                raise ValueError("FUNCTION arguments_schema type must be array or object")
        return self


class AssignmentCreate(AssignmentFields):
    pass


class AssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    total_score: Decimal | None = Field(default=None, gt=0)
    time_limit_ms: int | None = Field(default=None, ge=50, le=5_000)
    python_version: str | None = Field(default=None, pattern=r"^3\.12(?:\.\d+)?$")
    execution_mode: ExecutionMode | None = None
    entry_function: str | None = Field(default=None, max_length=128)
    arguments_schema: dict[str, Any] | None = None
    comparison_mode: ComparisonMode | None = None


class AssignmentRead(AssignmentFields, OrmModel):
    id: str
    demo_key: str | None
    analysis_input_version: int
    provenance: DataProvenance
    created_at: datetime
    updated_at: datetime


class RubricCriterionCreate(BaseModel):
    criterion_key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    max_score: Decimal = Field(gt=0)
    rules: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    active: bool = True
    origin: RubricOrigin = RubricOrigin.HUMAN


class RubricCriterionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    max_score: Decimal | None = Field(default=None, gt=0)
    rules: dict[str, Any] | None = None
    sort_order: int | None = None
    active: bool | None = None


class RubricApproval(BaseModel):
    approved_by: str = Field(min_length=1, max_length=200)


class RubricCriterionRead(OrmModel):
    id: str
    assignment_id: str
    criterion_key: str
    title: str
    description: str
    max_score: Decimal
    rules: dict[str, Any]
    sort_order: int
    active: bool
    origin: RubricOrigin
    approval_status: RubricStatus
    approved_by: str | None
    approved_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


class RubricParseRequest(BaseModel):
    policy_text: str = Field(min_length=1, max_length=50_000)


class RubricParseJobRead(OrmModel):
    id: str
    assignment_id: str
    status: AnalysisStatus
    provider: str
    model_name: str
    prompt_version: str
    provider_response_id: str | None
    input_fingerprint: str
    sanitized_input_hash: str | None
    external_data_manifest: dict[str, Any]
    uncertainties: list[str]
    error_message: str | None
    completed_at: datetime | None
    provenance: DataProvenance
    created_at: datetime
    updated_at: datetime


class TestCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    input_payload: JsonValue = None
    expected_output: JsonValue = None
    comparison_mode: ComparisonMode | None = None
    is_hidden: bool = False
    active: bool = True
    sort_order: int = 0


class TestCaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    input_payload: JsonValue = None
    expected_output: JsonValue = None
    comparison_mode: ComparisonMode | None = None
    is_hidden: bool | None = None
    active: bool | None = None
    sort_order: int | None = None


class TestCaseRead(OrmModel):
    id: str
    assignment_id: str
    name: str
    input_payload: JsonValue
    expected_output: JsonValue
    comparison_mode: ComparisonMode | None
    is_hidden: bool
    active: bool
    sort_order: int
    revision: int
    created_at: datetime
    updated_at: datetime


class TestCaseStudentRead(BaseModel):
    id: str
    name: str
    is_hidden: bool
    comparison_mode: ComparisonMode | None
    input_payload: JsonValue = None
    expected_output: JsonValue = None


class SubmissionCreate(BaseModel):
    assignment_id: str
    student_reference: str = Field(min_length=1, max_length=200)


class AssignmentSubmissionCreate(BaseModel):
    student_reference: str = Field(min_length=1, max_length=200)


class SubmissionRead(OrmModel):
    id: str
    assignment_id: str
    student_reference: str
    status: SubmissionStatus
    source_version: int
    provenance: DataProvenance
    created_at: datetime
    updated_at: datetime


class SourceFileCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str


class SourceFileRead(OrmModel):
    id: str
    submission_id: str
    filename: str
    content: str
    content_sha256: str
    revision: int
    is_current: bool
    created_at: datetime


class ExecutionRunCreate(BaseModel):
    runner_version: str = Field(min_length=1, max_length=100)
    image_digest: str | None = Field(default=None, max_length=255)
    status: ExecutionStatus = ExecutionStatus.PENDING
    run_metadata: dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(BaseModel):
    analyze_after_execution: bool = True


class AnalyzeRequest(BaseModel):
    execution_run_id: str | None = None


class ExecutionRunRead(OrmModel):
    id: str
    submission_id: str
    status: ExecutionStatus
    runner_version: str
    image_digest: str | None
    error_category: ErrorCategory | None
    exception_type: str | None
    signature_status: str | None
    started_at: datetime | None
    completed_at: datetime | None
    run_metadata: dict[str, Any]
    assignment_input_version: int
    source_version: int
    provenance: DataProvenance
    created_at: datetime


class ExecutionRunUpdate(BaseModel):
    status: ExecutionStatus | None = None
    error_category: ErrorCategory | None = None
    exception_type: str | None = Field(default=None, max_length=255)
    signature_status: str | None = Field(default=None, max_length=100)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    run_metadata: dict[str, Any] | None = None


class TestResultCreate(BaseModel):
    test_case_id: str
    status: TestResultStatus
    applied_comparison_mode: ComparisonMode
    actual_output: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    error_category: ErrorCategory | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    result_metadata: dict[str, Any] = Field(default_factory=dict)


class TestResultRead(OrmModel):
    id: str
    execution_run_id: str
    test_case_id: str
    status: TestResultStatus
    applied_comparison_mode: ComparisonMode
    actual_output: str | None
    stderr: str | None
    exit_code: int | None
    error_category: ErrorCategory | None
    duration_ms: float | None
    result_metadata: dict[str, Any]
    created_at: datetime


class ReviewerTestResultRead(TestResultRead):
    """Test result projection for the instructor-only review workspace.

    Hidden inputs and expected values belong only in this reviewer projection;
    student-facing endpoints and CSV exports deliberately use narrower models.
    """

    test_name: str
    is_hidden: bool
    input_payload: JsonValue
    expected_output: JsonValue
    stdout: str | None
    visibility: EvidenceVisibility


class EvidenceCreate(BaseModel):
    execution_run_id: str | None = None
    test_result_id: str | None = None
    source_file_id: str | None = None
    kind: EvidenceKind
    visibility: EvidenceVisibility = EvidenceVisibility.REVIEWER_ONLY
    summary: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    fingerprint: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_location(self) -> EvidenceCreate:
        if self.kind == EvidenceKind.SOURCE_CODE_LOCATION and not self.source_file_id:
            raise ValueError("SourceCodeLocation evidence requires source_file_id")
        if self.end_line is not None and self.start_line is None:
            raise ValueError("end_line requires start_line")
        if self.start_line is not None and self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line cannot precede start_line")
        return self


class EvidenceRead(OrmModel):
    id: str
    submission_id: str
    execution_run_id: str | None
    test_result_id: str | None
    source_file_id: str | None
    kind: EvidenceKind
    visibility: EvidenceVisibility
    summary: str
    details: dict[str, Any]
    start_line: int | None
    end_line: int | None
    fingerprint: str | None
    provenance: DataProvenance
    created_at: datetime


class RubricScoreRead(OrmModel):
    id: str
    rubric_criterion_id: str
    suggested_score: Decimal
    interpretation: str
    feedback: str | None
    model_reported_confidence: float | None
    primary_evidence: list[EvidenceRead] = Field(default_factory=list)


class RubricScoreCreate(BaseModel):
    rubric_criterion_id: str
    suggested_score: Decimal = Field(ge=0)
    interpretation: str = Field(
        min_length=1,
        description="Conservative evidence-bound interpretation; never a claim about private thought",
    )
    feedback: str | None = None
    model_reported_confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class AIAnalysisCreate(BaseModel):
    execution_run_id: str | None = None
    status: AnalysisStatus = AnalysisStatus.COMPLETED
    provider: str = Field(min_length=1, max_length=100)
    provider_response_id: str | None = Field(default=None, max_length=255)
    model_name: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)
    summary: str | None = None
    feedback: str | None = None
    model_reported_confidence: float | None = Field(default=None, ge=0, le=1)
    input_fingerprint: str = Field(min_length=1, max_length=128)
    sanitized_input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    external_data_manifest: dict[str, Any] = Field(default_factory=dict)
    token_usage: dict[str, Any] = Field(default_factory=dict)
    conflicting_evidence: bool = False
    rubric_scores: list[RubricScoreCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_external_provider_disclosure(self) -> AIAnalysisCreate:
        if self.provider.strip().lower() in {"openai", "external"}:
            if self.sanitized_input_hash is None:
                raise ValueError("external AI analyses require a sanitized_input_hash")
            fields_sent = self.external_data_manifest.get("fields_sent")
            if not isinstance(fields_sent, list):
                raise ValueError(
                    "external_data_manifest.fields_sent must disclose data sent to the provider"
                )
        return self


class AIAnalysisRead(OrmModel):
    id: str
    submission_id: str
    execution_run_id: str | None
    status: AnalysisStatus
    model_name: str
    provider: str
    provider_response_id: str | None
    prompt_version: str
    summary: str | None
    feedback: str | None
    model_reported_confidence: float | None
    review_required: bool
    review_reasons: list[str]
    input_fingerprint: str
    assignment_input_version: int
    source_version: int
    sanitized_input_hash: str | None
    external_data_manifest: dict[str, Any]
    token_usage: dict[str, Any]
    stale_reason: str | None
    provenance: DataProvenance
    rubric_scores: list[RubricScoreRead] = Field(default_factory=list)
    created_at: datetime


class HumanRubricScoreCreate(BaseModel):
    rubric_criterion_id: str
    awarded_score: Decimal = Field(ge=0)
    reason: str | None = None


class HumanReviewCreate(BaseModel):
    reviewer: str = Field(min_length=1, max_length=200)
    ai_analysis_id: str | None = None
    status: ReviewStatus = ReviewStatus.PENDING
    decision_reason: str | None = None
    scores: list[HumanRubricScoreCreate] = Field(default_factory=list)


class HumanRubricScoreRead(OrmModel):
    id: str
    rubric_criterion_id: str
    awarded_score: Decimal
    reason: str | None


class HumanReviewRead(OrmModel):
    id: str
    submission_id: str
    ai_analysis_id: str | None
    reviewer: str
    status: ReviewStatus
    decision_reason: str | None
    reviewed_assignment_version: int
    reviewed_source_version: int
    is_current: bool
    approved_at: datetime | None
    scores: list[HumanRubricScoreRead]
    created_at: datetime


class FinalGradeRead(BaseModel):
    submission_id: str
    human_review_id: str
    final_total: Decimal
    approved_at: datetime


class AssignmentOverviewRead(AssignmentRead):
    submission_count: int
    pending_review_count: int
    approved_count: int
    consistency_issue_count: int
    analyzed_percent: int
    rubric_ready: bool


class SubmissionReviewBundleRead(BaseModel):
    submission: SubmissionRead
    assignment: AssignmentRead
    source_file: SourceFileRead | None
    rubric_criteria: list[RubricCriterionRead]
    execution_run: ExecutionRunRead | None
    test_results: list[ReviewerTestResultRead]
    evidence: list[EvidenceRead]
    analysis: AIAnalysisRead | None
    human_reviews: list[HumanReviewRead]
    final_grade: FinalGradeRead | None
    analysis_summary: dict[str, Any] | None = None
    student_feedback: list[dict[str, Any]] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class DemoResetRequest(BaseModel):
    provenance: str = Field(pattern=r"^(FIXTURE|LIVE)$")


class DemoResetRead(BaseModel):
    assignment_id: str
    submission_ids: list[str]
    provenance: DataProvenance
    execution_jobs_queued: int
    analysis_jobs_queued: int


class ConsistencyIssueCreate(BaseModel):
    submission_id: str
    compared_submission_id: str | None = None
    analysis_id: str | None = None
    issue_type: str = Field(min_length=1, max_length=100)
    severity: ConsistencyIssueSeverity
    description: str = Field(min_length=1)
    test_status_vector: list[str] = Field(default_factory=list)
    error_category: str | None = Field(default=None, max_length=100)
    ast_feature_summary: dict[str, Any] = Field(default_factory=dict)
    exception_type: str | None = Field(default=None, max_length=255)
    signature_status: str | None = Field(default=None, max_length=100)


class ConsistencyIssueUpdate(BaseModel):
    status: ConsistencyIssueStatus
    resolution_note: str = Field(min_length=1)
    resolved_by: str = Field(min_length=1, max_length=200)


class ConsistencyIssueRead(OrmModel):
    id: str
    assignment_id: str
    submission_id: str
    compared_submission_id: str | None
    analysis_id: str | None
    issue_type: str
    severity: ConsistencyIssueSeverity
    status: ConsistencyIssueStatus
    potential_issue: bool
    description: str
    fingerprint_hash: str
    test_status_vector: list[str]
    error_category: str | None
    ast_feature_summary: dict[str, Any]
    exception_type: str | None
    signature_status: str | None
    resolution_note: str | None
    resolved_by: str | None
    created_at: datetime
    updated_at: datetime


class DeleteResponse(BaseModel):
    deleted: bool = True
    id: str
