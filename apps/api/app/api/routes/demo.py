from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.schemas.domain import DemoResetRead, DemoResetRequest
from app.services.demo_seed import reset_demo


router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset", response_model=DemoResetRead, status_code=status.HTTP_201_CREATED)
def reset_demo_data(
    payload: DemoResetRequest,
    session: Session = Depends(get_db),
) -> DemoResetRead:
    if not get_settings().demo_mode:
        raise ApiError(404, "DEMO_MODE_DISABLED", "Demo reset is disabled")
    live = payload.provenance == "LIVE"
    assignment, submissions = reset_demo(session, live=live)
    return DemoResetRead(
        assignment_id=assignment.id,
        submission_ids=[submission.id for submission in submissions],
        provenance=assignment.provenance,
        execution_jobs_queued=len(submissions) if live else 0,
        analysis_jobs_queued=0,
    )
