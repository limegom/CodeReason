from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
import re

from .schemas import AIAnalysisOutput, ErrorCategory


class AnalysisPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RubricBound:
    id: str
    max_score: float
    human_approved: bool = True
    evaluation_type: str = "hybrid"


@dataclass(frozen=True, slots=True)
class AnalysisPolicyContext:
    rubrics: tuple[RubricBound, ...]
    available_evidence_ids: frozenset[str]
    conflicting_evidence: bool = False
    execution_unavailable: bool = False
    low_confidence_threshold: float = 0.70
    evidence_kinds: Mapping[str, str] = field(default_factory=dict)
    student_visible_evidence_ids: frozenset[str] | None = None


def validate_analysis(
    output: AIAnalysisOutput,
    context: AnalysisPolicyContext,
) -> AIAnalysisOutput:
    """Validate a model response against deterministic grading rules."""

    private_thought_claim = re.compile(
        r"\b(?:the )?student (?:thought|intended|believes|knew|did not understand|understands)\b",
        re.IGNORECASE,
    )
    text_fields = [
        output.submission_summary.approach_summary,
        output.submission_summary.primary_issue,
        *output.submission_summary.strengths,
        *(item.reason for item in output.rubric_results),
        *(item.shows_evidence_of for item in output.feedback_to_student),
        *(item.likely_misconception for item in output.feedback_to_student),
    ]
    if any(private_thought_claim.search(text) for text in text_fields):
        raise AnalysisPolicyError(
            "analysis must describe observable evidence rather than a student's private thought"
        )

    approved = {item.id: item for item in context.rubrics if item.human_approved}
    received_ids = [item.rubric_id for item in output.rubric_results]
    if len(received_ids) != len(set(received_ids)):
        raise AnalysisPolicyError("duplicate rubric result")
    if set(received_ids) != set(approved):
        raise AnalysisPolicyError("analysis must cover exactly the human-approved rubrics")

    for result in output.rubric_results:
        rubric = approved[result.rubric_id]
        if abs(result.max_score - rubric.max_score) > 1e-9:
            raise AnalysisPolicyError(f"max score mismatch for {result.rubric_id}")
        unknown_evidence = set(result.evidence_ids) - context.available_evidence_ids
        if unknown_evidence:
            raise AnalysisPolicyError(
                f"unknown primary evidence for {result.rubric_id}: {sorted(unknown_evidence)}"
            )
        if result.suggested_score < result.max_score and not result.evidence_ids:
            raise AnalysisPolicyError(
                f"deduction without primary evidence for {result.rubric_id}"
            )
        cited_kinds = {
            context.evidence_kinds[evidence_id]
            for evidence_id in result.evidence_ids
            if evidence_id in context.evidence_kinds
        }
        if cited_kinds:
            dynamic = {"TestResult", "ExecutionError"}
            structural = {"ASTFinding", "StaticFinding", "SourceCodeLocation"}
            evaluation_type = rubric.evaluation_type.lower()
            insufficient_mix = (
                evaluation_type == "hybrid"
                and (not cited_kinds.intersection(dynamic) or not cited_kinds.intersection(structural))
            ) or (evaluation_type == "test" and not cited_kinds.intersection(dynamic))
            # A structural observation alone may inform review, but it cannot
            # establish conceptual understanding or silently finalize a score.
            if insufficient_mix:
                result.manual_review_required = True
        if (
            result.model_reported_confidence < context.low_confidence_threshold
            or context.conflicting_evidence
            or context.execution_unavailable
        ):
            result.manual_review_required = True

    for feedback in output.feedback_to_student:
        unknown_evidence = set(feedback.evidence_ids) - context.available_evidence_ids
        if unknown_evidence:
            raise AnalysisPolicyError(
                f"student feedback cites unknown evidence: {sorted(unknown_evidence)}"
            )
        if context.student_visible_evidence_ids is not None:
            unsafe_evidence = set(feedback.evidence_ids) - context.student_visible_evidence_ids
            if unsafe_evidence:
                raise AnalysisPolicyError(
                    "student feedback cites evidence that is not STUDENT_VISIBLE: "
                    f"{sorted(unsafe_evidence)}"
                )

    if context.execution_unavailable:
        output.submission_summary.error_category = ErrorCategory.EXECUTION_UNAVAILABLE
        if not any("execution" in item.lower() for item in output.uncertainties):
            output.uncertainties.append("Execution evidence was unavailable; human review is required.")
    return output
