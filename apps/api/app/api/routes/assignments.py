from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_entity
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import (
    Assignment,
    DataProvenance,
    RubricCriterion,
    RubricOrigin,
    RubricParseJob,
    RubricStatus,
    SourceFile,
    Submission,
    TestCase,
)
from app.schemas.domain import (
    AssignmentCreate,
    AssignmentRead,
    AssignmentSubmissionCreate,
    AssignmentUpdate,
    DeleteResponse,
    RubricApproval,
    RubricCriterionCreate,
    RubricCriterionRead,
    RubricCriterionUpdate,
    RubricParseJobRead,
    RubricParseRequest,
    SubmissionRead,
    TestCaseCreate,
    TestCaseRead,
    TestCaseStudentRead,
    TestCaseUpdate,
)
from app.services.evidence_policy import test_case_for_student
from app.services.staleness import invalidate_assignment_inputs
from app.services.ai_orchestrator import enqueue_rubric_parse


router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(payload: AssignmentCreate, session: Session = Depends(get_db)) -> Assignment:
    assignment = Assignment(**payload.model_dump())
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return assignment


@router.get("", response_model=list[AssignmentRead])
def list_assignments(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    session: Session = Depends(get_db),
) -> list[Assignment]:
    return list(
        session.scalars(select(Assignment).order_by(Assignment.created_at.desc()).offset(offset).limit(limit))
    )


@router.get("/{assignment_id}", response_model=AssignmentRead)
def get_assignment(assignment_id: str, session: Session = Depends(get_db)) -> Assignment:
    return require_entity(session, Assignment, assignment_id, "Assignment")


@router.post(
    "/{assignment_id}/submissions",
    response_model=SubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment_submission(
    assignment_id: str,
    payload: AssignmentSubmissionCreate,
    session: Session = Depends(get_db),
) -> Submission:
    require_entity(session, Assignment, assignment_id, "Assignment")
    submission = Submission(
        assignment_id=assignment_id,
        student_reference=payload.student_reference.strip(),
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


@router.get("/{assignment_id}/submissions", response_model=list[SubmissionRead])
def list_assignment_submissions(
    assignment_id: str,
    session: Session = Depends(get_db),
) -> list[Submission]:
    require_entity(session, Assignment, assignment_id, "Assignment")
    return list(
        session.scalars(
            select(Submission)
            .where(Submission.assignment_id == assignment_id)
            .order_by(Submission.created_at)
        )
    )


@router.post(
    "/{assignment_id}/submissions/upload",
    response_model=list[SubmissionRead],
    status_code=status.HTTP_201_CREATED,
)
async def upload_assignment_submissions(
    assignment_id: str,
    files: list[UploadFile] = File(...),
    student_reference_prefix: str = Form(default="student"),
    session: Session = Depends(get_db),
) -> list[Submission]:
    """Create one submission for each uploaded Python file."""

    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    settings = get_settings()
    if not files or len(files) > settings.upload_max_batch_files:
        raise ApiError(
            422,
            "INVALID_UPLOAD_BATCH",
            f"Upload between 1 and {settings.upload_max_batch_files} Python files",
        )

    validated: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    for upload in files:
        filename = (upload.filename or "").strip()
        if (
            PurePath(filename).name != filename
            or not filename.lower().endswith(".py")
            or filename in seen_names
        ):
            raise ApiError(422, "INVALID_SOURCE_FILE", "Each filename must be a unique .py basename")
        raw = await upload.read(settings.upload_max_file_bytes + 1)
        if len(raw) > settings.upload_max_file_bytes:
            raise ApiError(413, "SOURCE_FILE_TOO_LARGE", "A source file exceeds the configured limit")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApiError(422, "INVALID_SOURCE_ENCODING", "Python source must be UTF-8") from exc
        if not content or "\x00" in content:
            raise ApiError(422, "INVALID_SOURCE_FILE", "Python source must be non-empty text")
        seen_names.add(filename)
        validated.append((filename, content))

    created: list[Submission] = []
    prefix = student_reference_prefix.strip() or "student"
    for index, (filename, content) in enumerate(validated, start=1):
        submission = Submission(
            assignment_id=assignment.id,
            student_reference=f"{prefix}-{index:02d}",
            # Uploaded code never inherits demo-fixture provenance.
            provenance=DataProvenance.STORED_LIVE,
            source_version=1,
        )
        session.add(submission)
        session.flush()
        session.add(
            SourceFile(
                submission_id=submission.id,
                filename=filename,
                content=content,
                content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                revision=1,
                is_current=True,
            )
        )
        created.append(submission)
    session.commit()
    for submission in created:
        session.refresh(submission)
    return created


@router.patch("/{assignment_id}", response_model=AssignmentRead)
def update_assignment(
    assignment_id: str,
    payload: AssignmentUpdate,
    session: Session = Depends(get_db),
) -> Assignment:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    values = {
        "title": assignment.title,
        "description": assignment.description,
        "total_score": assignment.total_score,
        "time_limit_ms": assignment.time_limit_ms,
        "python_version": assignment.python_version,
        "execution_mode": assignment.execution_mode,
        "entry_function": assignment.entry_function,
        "arguments_schema": assignment.arguments_schema,
        "comparison_mode": assignment.comparison_mode,
    }
    values.update(payload.model_dump(exclude_unset=True))
    validated = AssignmentCreate.model_validate(values)
    changed = any(getattr(assignment, key) != value for key, value in validated.model_dump().items())
    if changed:
        for key, value in validated.model_dump().items():
            setattr(assignment, key, value)
        invalidate_assignment_inputs(session, assignment, "Assignment execution or grading input changed")
        session.commit()
        session.refresh(assignment)
    return assignment


@router.delete("/{assignment_id}", response_model=DeleteResponse)
def delete_assignment(assignment_id: str, session: Session = Depends(get_db)) -> DeleteResponse:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    session.delete(assignment)
    session.commit()
    return DeleteResponse(id=assignment_id)


def _criterion_for_assignment(
    session: Session, assignment_id: str, criterion_id: str
) -> RubricCriterion:
    criterion = require_entity(session, RubricCriterion, criterion_id, "Rubric criterion")
    if criterion.assignment_id != assignment_id:
        raise ApiError(404, "NOT_FOUND", "Rubric criterion was not found for this assignment")
    return criterion


@router.post(
    "/{assignment_id}/rubrics",
    response_model=RubricCriterionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_rubric_criterion(
    assignment_id: str,
    payload: RubricCriterionCreate,
    session: Session = Depends(get_db),
) -> RubricCriterion:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    # Model-structured criteria remain drafts until a person approves them.
    approval_status = RubricStatus.DRAFT
    criterion = RubricCriterion(
        assignment_id=assignment.id,
        approval_status=approval_status,
        **payload.model_dump(),
    )
    session.add(criterion)
    invalidate_assignment_inputs(session, assignment, "Rubric criterion added")
    session.commit()
    session.refresh(criterion)
    return criterion


@router.get("/{assignment_id}/rubrics", response_model=list[RubricCriterionRead])
def list_rubric_criteria(
    assignment_id: str, session: Session = Depends(get_db)
) -> list[RubricCriterion]:
    require_entity(session, Assignment, assignment_id, "Assignment")
    return list(
        session.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.assignment_id == assignment_id)
            .order_by(RubricCriterion.sort_order, RubricCriterion.created_at)
        )
    )


@router.get("/{assignment_id}/rubrics/{criterion_id}", response_model=RubricCriterionRead)
def get_rubric_criterion(
    assignment_id: str, criterion_id: str, session: Session = Depends(get_db)
) -> RubricCriterion:
    return _criterion_for_assignment(session, assignment_id, criterion_id)


@router.patch("/{assignment_id}/rubrics/{criterion_id}", response_model=RubricCriterionRead)
def update_rubric_criterion(
    assignment_id: str,
    criterion_id: str,
    payload: RubricCriterionUpdate,
    session: Session = Depends(get_db),
) -> RubricCriterion:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    criterion = _criterion_for_assignment(session, assignment_id, criterion_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes and any(getattr(criterion, key) != value for key, value in changes.items()):
        for key, value in changes.items():
            setattr(criterion, key, value)
        criterion.revision += 1
        criterion.approval_status = RubricStatus.DRAFT
        criterion.approved_by = None
        criterion.approved_at = None
        invalidate_assignment_inputs(session, assignment, "Rubric criterion changed")
        session.commit()
        session.refresh(criterion)
    return criterion


@router.post("/{assignment_id}/rubrics/{criterion_id}/approve", response_model=RubricCriterionRead)
def approve_rubric_criterion(
    assignment_id: str,
    criterion_id: str,
    payload: RubricApproval,
    session: Session = Depends(get_db),
) -> RubricCriterion:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    criterion = _criterion_for_assignment(session, assignment_id, criterion_id)
    if criterion.approval_status != RubricStatus.HUMAN_APPROVED:
        criterion.approval_status = RubricStatus.HUMAN_APPROVED
        criterion.approved_by = payload.approved_by.strip()
        criterion.approved_at = datetime.now(timezone.utc)
        criterion.revision += 1
        invalidate_assignment_inputs(session, assignment, "Rubric criterion human approval changed")
        session.commit()
        session.refresh(criterion)
    return criterion


@router.delete("/{assignment_id}/rubrics/{criterion_id}", response_model=DeleteResponse)
def delete_rubric_criterion(
    assignment_id: str, criterion_id: str, session: Session = Depends(get_db)
) -> DeleteResponse:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    criterion = _criterion_for_assignment(session, assignment_id, criterion_id)
    # Score history references this row, so archive it instead of deleting it.
    if criterion.active or criterion.approval_status != RubricStatus.ARCHIVED:
        criterion.active = False
        criterion.approval_status = RubricStatus.ARCHIVED
        criterion.approved_by = None
        criterion.approved_at = None
        criterion.revision += 1
        invalidate_assignment_inputs(session, assignment, "Rubric criterion archived")
        session.commit()
    return DeleteResponse(id=criterion_id)


@router.post(
    "/{assignment_id}/rubrics/parse",
    response_model=RubricParseJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def parse_rubric(
    assignment_id: str,
    payload: RubricParseRequest,
    session: Session = Depends(get_db),
) -> RubricParseJob:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    return enqueue_rubric_parse(
        session,
        assignment,
        policy_text=payload.policy_text,
    )


@router.get(
    "/{assignment_id}/rubrics/parse-jobs/{job_id}",
    response_model=RubricParseJobRead,
)
def get_rubric_parse_job(
    assignment_id: str,
    job_id: str,
    session: Session = Depends(get_db),
) -> RubricParseJob:
    job = require_entity(session, RubricParseJob, job_id, "Rubric parse job")
    if job.assignment_id != assignment_id:
        raise ApiError(404, "NOT_FOUND", "Rubric parse job was not found for this assignment")
    return job


def _test_case_for_assignment(session: Session, assignment_id: str, test_case_id: str) -> TestCase:
    test_case = require_entity(session, TestCase, test_case_id, "Test case")
    if test_case.assignment_id != assignment_id:
        raise ApiError(404, "NOT_FOUND", "Test case was not found for this assignment")
    return test_case


@router.post(
    "/{assignment_id}/test-cases", response_model=TestCaseRead, status_code=status.HTTP_201_CREATED
)
def create_test_case(
    assignment_id: str, payload: TestCaseCreate, session: Session = Depends(get_db)
) -> TestCase:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    test_case = TestCase(assignment_id=assignment.id, **payload.model_dump())
    session.add(test_case)
    invalidate_assignment_inputs(session, assignment, "Test case added")
    session.commit()
    session.refresh(test_case)
    return test_case


@router.get("/{assignment_id}/test-cases", response_model=list[TestCaseRead])
def list_test_cases(assignment_id: str, session: Session = Depends(get_db)) -> list[TestCase]:
    require_entity(session, Assignment, assignment_id, "Assignment")
    return list(
        session.scalars(
            select(TestCase)
            .where(TestCase.assignment_id == assignment_id)
            .order_by(TestCase.sort_order, TestCase.created_at)
        )
    )


@router.get("/{assignment_id}/test-cases/student", response_model=list[TestCaseStudentRead])
def list_test_cases_for_student(
    assignment_id: str, session: Session = Depends(get_db)
) -> list[dict]:
    test_cases = list_test_cases(assignment_id, session)
    return [test_case_for_student(test_case) for test_case in test_cases]


@router.get("/{assignment_id}/test-cases/{test_case_id}", response_model=TestCaseRead)
def get_test_case(
    assignment_id: str, test_case_id: str, session: Session = Depends(get_db)
) -> TestCase:
    return _test_case_for_assignment(session, assignment_id, test_case_id)


@router.patch("/{assignment_id}/test-cases/{test_case_id}", response_model=TestCaseRead)
def update_test_case(
    assignment_id: str,
    test_case_id: str,
    payload: TestCaseUpdate,
    session: Session = Depends(get_db),
) -> TestCase:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    test_case = _test_case_for_assignment(session, assignment_id, test_case_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes and any(getattr(test_case, key) != value for key, value in changes.items()):
        for key, value in changes.items():
            setattr(test_case, key, value)
        test_case.revision += 1
        invalidate_assignment_inputs(session, assignment, "Test case changed")
        session.commit()
        session.refresh(test_case)
    return test_case


@router.delete("/{assignment_id}/test-cases/{test_case_id}", response_model=DeleteResponse)
def delete_test_case(
    assignment_id: str, test_case_id: str, session: Session = Depends(get_db)
) -> DeleteResponse:
    assignment = require_entity(session, Assignment, assignment_id, "Assignment")
    test_case = _test_case_for_assignment(session, assignment_id, test_case_id)
    # Test results retain this foreign key; deactivate the definition in place.
    if test_case.active:
        test_case.active = False
        test_case.revision += 1
        invalidate_assignment_inputs(session, assignment, "Test case deactivated")
        session.commit()
    return DeleteResponse(id=test_case_id)
