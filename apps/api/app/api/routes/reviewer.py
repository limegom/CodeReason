from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_entity
from app.db import get_db
from app.errors import ApiError
from app.models import Assignment, Submission
from app.schemas.domain import AssignmentOverviewRead, SubmissionReviewBundleRead
from app.services.read_models import assignment_overviews, submission_review_bundle


router = APIRouter(prefix="/reviewer", tags=["reviewer read models"])


@router.get("/assignments", response_model=list[AssignmentOverviewRead])
def list_assignment_overviews(session: Session = Depends(get_db)) -> list[dict]:
    return assignment_overviews(session)


@router.get(
    "/assignments/{assignment_id}/submissions",
    response_model=list[SubmissionReviewBundleRead],
)
def list_assignment_review_bundles(
    assignment_id: str,
    session: Session = Depends(get_db),
) -> list[dict]:
    require_entity(session, Assignment, assignment_id, "Assignment")
    submission_ids = session.scalars(
        select(Submission.id)
        .where(Submission.assignment_id == assignment_id)
        .order_by(Submission.created_at)
    ).all()
    return [
        bundle
        for submission_id in submission_ids
        if (bundle := submission_review_bundle(session, submission_id)) is not None
    ]


@router.get("/submissions/{submission_id}", response_model=SubmissionReviewBundleRead)
def get_submission_review_bundle(
    submission_id: str,
    session: Session = Depends(get_db),
) -> dict:
    bundle = submission_review_bundle(session, submission_id)
    if bundle is None:
        raise ApiError(404, "NOT_FOUND", "Submission was not found", {"id": submission_id})
    return bundle
