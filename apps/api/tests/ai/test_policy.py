import pytest

from app.ai.policy import (
    AnalysisPolicyContext,
    AnalysisPolicyError,
    RubricBound,
    validate_analysis,
    withhold_unsafe_student_feedback,
)
from app.ai.schemas import AIAnalysisOutput, StudentFeedbackItem


def make_output(*, score: float = 3, evidence_ids: list[str] | None = None, confidence: float = 0.9):
    return AIAnalysisOutput.model_validate(
        {
            "submission_summary": {
                "error_category": "LOGIC",
                "approach_summary": "The code shows evidence of a row-building approach.",
                "strengths": ["Uses a loop visible in the source."],
                "primary_issue": "Observed output differs from the expected value.",
            },
            "rubric_results": [
                {
                    "rubric_id": "r1",
                    "max_score": 5,
                    "suggested_score": score,
                    "model_reported_confidence": confidence,
                    "reason": "The failed test suggests an indexing issue.",
                    "evidence_ids": evidence_ids or [],
                    "manual_review_required": False,
                }
            ],
            "feedback_to_student": [],
            "uncertainties": [],
        }
    )


def context(**overrides):
    values = {
        "rubrics": (RubricBound("r1", 5),),
        "available_evidence_ids": frozenset({"ev-1"}),
    }
    values.update(overrides)
    return AnalysisPolicyContext(**values)


def test_rejects_deduction_without_primary_evidence():
    with pytest.raises(AnalysisPolicyError, match="deduction without"):
        validate_analysis(make_output(), context())


def test_rejects_unknown_evidence():
    with pytest.raises(AnalysisPolicyError, match="unknown primary evidence"):
        validate_analysis(make_output(evidence_ids=["invented"]), context())


def test_low_model_reported_confidence_requires_review():
    output = validate_analysis(make_output(evidence_ids=["ev-1"], confidence=0.4), context())
    assert output.rubric_results[0].manual_review_required is True


def test_execution_unavailable_requires_review_and_uncertainty():
    output = validate_analysis(
        make_output(evidence_ids=["ev-1"]),
        context(execution_unavailable=True),
    )
    assert output.rubric_results[0].manual_review_required is True
    assert output.submission_summary.error_category == "EXECUTION_UNAVAILABLE"
    assert output.uncertainties


def test_student_feedback_cannot_cite_reviewer_only_evidence():
    output = make_output(evidence_ids=["ev-1"])
    output.feedback_to_student = [
        StudentFeedbackItem(
            concept="Hidden edge case",
            shows_evidence_of="The visible source shows an observable structure.",
            likely_misconception="A likely misconception requires review.",
            next_step="Check a visible example.",
            evidence_ids=["ev-1"],
        )
    ]
    with pytest.raises(AnalysisPolicyError, match="not STUDENT_VISIBLE"):
        validate_analysis(
            output,
            context(student_visible_evidence_ids=frozenset()),
        )


def test_withholds_complete_unsafe_feedback_items() -> None:
    output = make_output(evidence_ids=["visible"])
    output.feedback_to_student = [
        StudentFeedbackItem(
            concept="Visible behavior",
            shows_evidence_of="The visible test shows an observable mismatch.",
            likely_misconception="The output pattern suggests an indexing misconception.",
            next_step="Trace the visible example.",
            evidence_ids=["visible"],
        ),
        StudentFeedbackItem(
            concept="Hidden behavior",
            shows_evidence_of="Unsafe reviewer-only interpretation.",
            likely_misconception="Unsafe reviewer-only interpretation.",
            next_step="Unsafe reviewer-only guidance.",
            evidence_ids=["reviewer-only"],
        ),
        StudentFeedbackItem(
            concept="Unsupported behavior",
            shows_evidence_of="Unsupported interpretation.",
            likely_misconception="Unsupported interpretation.",
            next_step="Unsupported guidance.",
            evidence_ids=[],
        ),
    ]
    policy_context = context(
        available_evidence_ids=frozenset({"visible", "reviewer-only"}),
        student_visible_evidence_ids=frozenset({"visible"}),
    )

    withheld = withhold_unsafe_student_feedback(output, policy_context)

    assert withheld is True
    assert [item.concept for item in output.feedback_to_student] == ["Visible behavior"]
    assert output.uncertainties
    validate_analysis(output, policy_context)


def test_private_thought_claim_is_rejected():
    output = make_output(evidence_ids=["ev-1"])
    output.submission_summary.approach_summary = "The student thought indexing began at one."
    with pytest.raises(AnalysisPolicyError, match="private thought"):
        validate_analysis(output, context())
