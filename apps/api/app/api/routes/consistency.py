from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_entity
from app.db import get_db
from app.errors import ApiError
from app.models import AIAnalysis, Assignment, ConsistencyIssue, ConsistencyIssueStatus, Submission
from app.schemas.domain import (
    ConsistencyIssueCreate,
    ConsistencyIssueRead,
    ConsistencyIssueUpdate,
)


router = APIRouter(prefix="/assignments/{assignment_id}/consistency-issues", tags=["consistency"])


def _fingerprint(payload: ConsistencyIssueCreate) -> str:
    value = {
        "test_status_vector": payload.test_status_vector,
        "error_category": payload.error_category,
        "ast_feature_summary": payload.ast_feature_summary,
        "exception_type": payload.exception_type,
        "signature_status": payload.signature_status,
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post("", response_model=ConsistencyIssueRead, status_code=status.HTTP_201_CREATED)
def create_consistency_issue(
    assignment_id: str,
    payload: ConsistencyIssueCreate,
    session: Session = Depends(get_db),
) -> ConsistencyIssue:
    require_entity(session, Assignment, assignment_id, "Assignment")
    submission = require_entity(session, Submission, payload.submission_id, "Submission")
    if submission.assignment_id != assignment_id:
        raise ApiError(422, "SUBMISSION_MISMATCH", "Submission belongs to another assignment")
    if payload.compared_submission_id:
        compared = require_entity(
            session, Submission, payload.compared_submission_id, "Compared submission"
        )
        if compared.assignment_id != assignment_id:
            raise ApiError(422, "SUBMISSION_MISMATCH", "Compared submission belongs elsewhere")
    if payload.analysis_id:
        analysis = require_entity(session, AIAnalysis, payload.analysis_id, "AI analysis")
        if analysis.submission_id != submission.id:
            raise ApiError(422, "ANALYSIS_MISMATCH", "AI analysis belongs to another submission")

    description = payload.description.strip()
    if not description.lower().startswith("potential issue"):
        description = f"Potential issue: {description}"
    issue = ConsistencyIssue(
        assignment_id=assignment_id,
        submission_id=payload.submission_id,
        compared_submission_id=payload.compared_submission_id,
        analysis_id=payload.analysis_id,
        issue_type=payload.issue_type,
        severity=payload.severity,
        status=ConsistencyIssueStatus.OPEN,
        potential_issue=True,
        description=description,
        fingerprint_hash=_fingerprint(payload),
        test_status_vector=payload.test_status_vector,
        error_category=payload.error_category,
        ast_feature_summary=payload.ast_feature_summary,
        exception_type=payload.exception_type,
        signature_status=payload.signature_status,
    )
    session.add(issue)
    session.commit()
    session.refresh(issue)
    return issue


@router.get("", response_model=list[ConsistencyIssueRead])
def list_consistency_issues(
    assignment_id: str,
    issue_status: ConsistencyIssueStatus | None = Query(default=None, alias="status"),
    session: Session = Depends(get_db),
) -> list[ConsistencyIssue]:
    require_entity(session, Assignment, assignment_id, "Assignment")
    statement = select(ConsistencyIssue).where(ConsistencyIssue.assignment_id == assignment_id)
    if issue_status is not None:
        statement = statement.where(ConsistencyIssue.status == issue_status)
    return list(session.scalars(statement.order_by(ConsistencyIssue.created_at.desc())))


@router.patch("/{issue_id}", response_model=ConsistencyIssueRead)
def update_consistency_issue(
    assignment_id: str,
    issue_id: str,
    payload: ConsistencyIssueUpdate,
    session: Session = Depends(get_db),
) -> ConsistencyIssue:
    issue = require_entity(session, ConsistencyIssue, issue_id, "Consistency issue")
    if issue.assignment_id != assignment_id:
        raise ApiError(404, "NOT_FOUND", "Consistency issue was not found for this assignment")
    issue.status = payload.status
    issue.resolution_note = payload.resolution_note
    issue.resolved_by = payload.resolved_by
    session.commit()
    session.refresh(issue)
    return issue

