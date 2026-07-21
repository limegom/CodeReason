from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AIAnalysis,
    AnalysisStatus,
    HumanReview,
    HumanRubricScore,
    RubricCriterion,
    RubricStatus,
    Submission,
    SubmissionStatus,
    TestCase as DbTestCase,
    TestResult as DbTestResult,
)
from app.services.demo_seed import reset_demo
from app.services.grading_operations import build_assignment_csv
from app.services.read_models import submission_review_bundle


def test_archiving_a_used_rubric_preserves_human_review_audit_history(
    db_session: Session,
    client: TestClient,
) -> None:
    assignment, submissions = reset_demo(db_session, live=False)
    criterion = db_session.scalar(
        select(RubricCriterion)
        .where(RubricCriterion.assignment_id == assignment.id)
        .order_by(RubricCriterion.sort_order)
    )
    assert criterion is not None
    human_score_count = db_session.scalar(
        select(func.count()).select_from(HumanRubricScore).where(
            HumanRubricScore.rubric_criterion_id == criterion.id
        )
    )
    assert human_score_count == 1

    response = client.delete(
        f"/api/assignments/{assignment.id}/rubrics/{criterion.id}"
    )

    assert response.status_code == 200
    db_session.expire_all()
    archived = db_session.get(RubricCriterion, criterion.id)
    assert archived is not None
    assert archived.active is False
    assert archived.approval_status == RubricStatus.ARCHIVED
    assert db_session.scalar(
        select(func.count()).select_from(HumanRubricScore).where(
            HumanRubricScore.rubric_criterion_id == criterion.id
        )
    ) == human_score_count
    current_review = db_session.scalar(
        select(HumanReview).where(HumanReview.submission_id == submissions[0].id)
    )
    assert current_review is not None
    assert current_review.is_current is False
    assert db_session.get(Submission, submissions[0].id).status == SubmissionStatus.REVIEW_REQUIRED
    assert client.get(f"/api/submissions/{submissions[0].id}/final-grade").status_code == 409


def test_deactivating_a_used_test_preserves_test_results_and_stales_analysis(
    db_session: Session,
    client: TestClient,
) -> None:
    assignment, _submissions = reset_demo(db_session, live=False)
    test_case = db_session.scalar(
        select(DbTestCase)
        .where(DbTestCase.assignment_id == assignment.id)
        .order_by(DbTestCase.sort_order)
    )
    assert test_case is not None
    result_count = db_session.scalar(
        select(func.count()).select_from(DbTestResult).where(
            DbTestResult.test_case_id == test_case.id
        )
    )
    assert result_count == 5

    response = client.delete(
        f"/api/assignments/{assignment.id}/test-cases/{test_case.id}"
    )

    assert response.status_code == 200
    db_session.expire_all()
    preserved = db_session.get(DbTestCase, test_case.id)
    assert preserved is not None
    assert preserved.active is False
    assert db_session.scalar(
        select(func.count()).select_from(DbTestResult).where(
            DbTestResult.test_case_id == test_case.id
        )
    ) == result_count
    statuses = set(
        db_session.scalars(
            select(AIAnalysis.status).where(
                AIAnalysis.submission_id.in_(
                    select(Submission.id).where(Submission.assignment_id == assignment.id)
                )
            )
        )
    )
    assert statuses == {AnalysisStatus.STALE}


def test_stale_analysis_feedback_is_not_exported_as_current_student_feedback(
    db_session: Session,
) -> None:
    assignment, submissions = reset_demo(db_session, live=False)
    stale_submission = submissions[3]

    bundle = submission_review_bundle(db_session, stale_submission.id)
    rows = list(csv.DictReader(io.StringIO(build_assignment_csv(db_session, assignment))))
    stale_row = next(row for row in rows if row["filename"] == "hardcoded_solution.py")

    assert bundle is not None
    assert bundle["analysis"].status == AnalysisStatus.STALE
    assert bundle["student_feedback"] == []
    assert stale_row["short_feedback"] == ""
