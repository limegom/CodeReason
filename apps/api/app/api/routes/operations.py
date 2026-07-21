from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_entity
from app.db import get_db
from app.models import Assignment
from app.schemas.domain import ConsistencyIssueRead
from app.services.grading_operations import build_assignment_csv, run_consistency_check


router = APIRouter(tags=["grading operations"])


def _assignment(session: Session, assignment_id: str) -> Assignment:
    assignment = session.scalar(
        select(Assignment)
        .where(Assignment.id == assignment_id)
        .options(
            selectinload(Assignment.submissions),
            selectinload(Assignment.rubric_criteria),
        )
    )
    if assignment is None:
        return require_entity(session, Assignment, assignment_id, "Assignment")
    return assignment


@router.post(
    "/assignments/{assignment_id}/consistency-check",
    response_model=list[ConsistencyIssueRead],
    status_code=status.HTTP_200_OK,
)
def check_assignment_consistency(
    assignment_id: str,
    session: Session = Depends(get_db),
):
    return run_consistency_check(session, _assignment(session, assignment_id))


@router.get("/assignments/{assignment_id}/export.csv")
def export_assignment_csv(
    assignment_id: str,
    session: Session = Depends(get_db),
) -> Response:
    assignment = _assignment(session, assignment_id)
    content = build_assignment_csv(session, assignment)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="codereason-{assignment.id}.csv"',
            "X-CodeReason-Hidden-Test-Values": "withheld",
        },
    )
