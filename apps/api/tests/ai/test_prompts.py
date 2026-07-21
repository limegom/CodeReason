import json

from app.ai.prompts import GRADING_SYSTEM_PROMPT, PROMPT_VERSION, build_grading_payload
from app.ai.schemas import StudentFeedbackItem


def test_grading_prompt_separates_reviewer_and_student_visible_evidence() -> None:
    assert PROMPT_VERSION == "grading-derived-analysis-v2"
    assert "student_feedback_allowed_evidence_ids" in GRADING_SYSTEM_PROMPT
    assert "REVIEWER_ONLY evidence" in GRADING_SYSTEM_PROMPT


def test_grading_payload_lists_student_feedback_evidence_allowlist() -> None:
    payload = json.loads(
        build_grading_payload(
            assignment_description="Synthetic assignment",
            approved_rubric=[],
            redacted_source_code="pass",
            primary_evidence=[],
            student_feedback_allowed_evidence_ids=["visible-1"],
            maximum_total=1,
        )
    )
    assert payload["student_feedback_allowed_evidence_ids"] == ["visible-1"]


def test_student_feedback_schema_requires_student_visible_evidence() -> None:
    schema = StudentFeedbackItem.model_json_schema()
    description = schema["properties"]["evidence_ids"]["description"]
    assert "STUDENT_VISIBLE" in description
