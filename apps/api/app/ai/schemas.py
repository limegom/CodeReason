from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Score = Annotated[float, Field(ge=0)]
Confidence = Annotated[float, Field(ge=0, le=1)]


class ErrorCategory(StrEnum):
    NONE = "NONE"
    SYNTAX = "SYNTAX"
    RUNTIME = "RUNTIME"
    LOGIC = "LOGIC"
    TIMEOUT = "TIMEOUT"
    MIXED = "MIXED"
    EXECUTION_UNAVAILABLE = "EXECUTION_UNAVAILABLE"


class SubmissionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_category: ErrorCategory
    approach_summary: str = Field(
        description="Describe only the approach visible in code and primary evidence."
    )
    strengths: list[str]
    primary_issue: str


class RubricAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_id: str
    max_score: Score
    suggested_score: Score
    model_reported_confidence: Confidence
    reason: str
    evidence_ids: list[str]
    manual_review_required: bool

    @model_validator(mode="after")
    def score_is_bounded(self) -> "RubricAnalysisResult":
        if self.suggested_score > self.max_score:
            raise ValueError("suggested_score cannot exceed max_score")
        return self


class StudentFeedbackItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str
    shows_evidence_of: str
    likely_misconception: str
    next_step: str
    evidence_ids: list[str]


class AIAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_summary: SubmissionSummary
    rubric_results: list[RubricAnalysisResult]
    feedback_to_student: list[StudentFeedbackItem]
    uncertainties: list[str]


class DeductionRuleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str
    score: float | None = None
    points_to_deduct: float | None = None

    @model_validator(mode="after")
    def exactly_one_effect(self) -> "DeductionRuleOutput":
        if (self.score is None) == (self.points_to_deduct is None):
            raise ValueError("provide exactly one of score or points_to_deduct")
        return self


class PartialCreditGuidanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str
    suggested_score_range: tuple[float, float]

    @model_validator(mode="after")
    def valid_range(self) -> "PartialCreditGuidanceOutput":
        low, high = self.suggested_score_range
        if low < 0 or high < low:
            raise ValueError("invalid suggested score range")
        return self


class ParsedRubricItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    max_score: Score
    evaluation_type: Literal["test", "ast", "static", "hybrid", "manual"]
    required_evidence: list[str]
    deduction_rules: list[DeductionRuleOutput]
    partial_credit_guidance: list[PartialCreditGuidanceOutput]
    approval_status: Literal["DRAFT"] = "DRAFT"


class RubricParseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ParsedRubricItem]
    uncertainties: list[str]

