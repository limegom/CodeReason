from __future__ import annotations

import pytest

from decimal import Decimal

from app.models import Assignment, RubricCriterion, RubricStatus
from app.services.grading_policy import rubric_is_grading_ready


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (RubricStatus.DRAFT, False),
        (RubricStatus.AI_STRUCTURED, False),
        (RubricStatus.HUMAN_APPROVED, True),
        (RubricStatus.ARCHIVED, False),
    ],
)
def test_only_a_human_approved_rubric_is_grading_ready(
    status: RubricStatus,
    expected: bool,
) -> None:
    criterion = RubricCriterion(approval_status=status, active=True)

    assert rubric_is_grading_ready(criterion) is expected


def test_assignment_rubric_must_match_declared_total_score():
    assignment = Assignment(total_score=Decimal("20"))
    assignment.rubric_criteria = [
        RubricCriterion(
            max_score=Decimal("10"),
            approval_status=RubricStatus.HUMAN_APPROVED,
            active=True,
        )
    ]
    assert rubric_is_grading_ready(assignment) is False
    assignment.rubric_criteria[0].max_score = Decimal("20")
    assert rubric_is_grading_ready(assignment) is True
