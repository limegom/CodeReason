from __future__ import annotations

from enum import StrEnum


class ExecutionMode(StrEnum):
    FUNCTION = "FUNCTION"
    STDIN_STDOUT = "STDIN_STDOUT"


class ComparisonMode(StrEnum):
    EXACT = "EXACT"
    IGNORE_FINAL_NEWLINE = "IGNORE_FINAL_NEWLINE"
    TRIM_TRAILING_WHITESPACE = "TRIM_TRAILING_WHITESPACE"
    TOKEN_BASED = "TOKEN_BASED"
    JSON_VALUE = "JSON_VALUE"


class DataProvenance(StrEnum):
    """Origin of persisted demo or live computation records.

    Provenance is data, not a UI guess based on whether an HTTP request worked.
    """

    LIVE = "LIVE"
    STORED_LIVE = "STORED_LIVE"
    DEMO_FIXTURE = "DEMO_FIXTURE"
    UNAVAILABLE = "UNAVAILABLE"


class RubricStatus(StrEnum):
    DRAFT = "DRAFT"
    AI_STRUCTURED = "AI_STRUCTURED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    ARCHIVED = "ARCHIVED"


class RubricOrigin(StrEnum):
    HUMAN = "HUMAN"
    AI_STRUCTURED = "AI_STRUCTURED"


class EvidenceKind(StrEnum):
    """Closed set of primary, directly inspectable evidence kinds."""

    TEST_RESULT = "TestResult"
    EXECUTION_ERROR = "ExecutionError"
    AST_FINDING = "ASTFinding"
    STATIC_FINDING = "StaticFinding"
    SOURCE_CODE_LOCATION = "SourceCodeLocation"


class EvidenceVisibility(StrEnum):
    INTERNAL = "INTERNAL"
    REVIEWER_ONLY = "REVIEWER_ONLY"
    STUDENT_VISIBLE = "STUDENT_VISIBLE"


class SubmissionStatus(StrEnum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    FAILED = "FAILED"


class ExecutionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    UNAVAILABLE = "UNAVAILABLE"


class TestResultStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    TIMED_OUT = "TIMED_OUT"
    SKIPPED = "SKIPPED"


class ErrorCategory(StrEnum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIMEOUT = "TIMEOUT"
    WRONG_ANSWER = "WRONG_ANSWER"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    EXECUTION_UNAVAILABLE = "EXECUTION_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AnalysisStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class ReviewTrigger(StrEnum):
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    EXECUTION_UNAVAILABLE = "EXECUTION_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    LOW_MODEL_REPORTED_CONFIDENCE = "LOW_MODEL_REPORTED_CONFIDENCE"
    STALE_INPUT = "STALE_INPUT"


class ConsistencyIssueStatus(StrEnum):
    OPEN = "OPEN"
    DISMISSED = "DISMISSED"
    RESOLVED = "RESOLVED"


class ConsistencyIssueSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
