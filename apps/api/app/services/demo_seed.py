from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AIAnalysis,
    AnalysisStatus,
    Assignment,
    ComparisonMode,
    ConsistencyIssue,
    ConsistencyIssueSeverity,
    DataProvenance,
    ErrorCategory,
    Evidence,
    EvidenceKind,
    EvidenceVisibility,
    ExecutionMode,
    ExecutionRun,
    ExecutionStatus,
    HumanReview,
    HumanRubricScore,
    ReviewStatus,
    RubricCriterion,
    RubricOrigin,
    RubricScore,
    RubricStatus,
    SourceFile,
    Submission,
    SubmissionStatus,
    TestCase,
    TestResult,
    TestResultStatus,
)


DEMO_KEY = "matrix-transformation-v1"

SOURCES = {
    "correct_solution.py": """def make_matrix(data, rows, cols):
    if rows * cols != len(data):
        raise ValueError("invalid dimensions")
    return [data[index:index + cols] for index in range(0, len(data), cols)]
""",
    "idea_correct_output_wrong.py": """def make_matrix(data, rows, cols):
    matrix = []
    for row in range(rows):
        current = []
        for column in range(cols):
            index = row * cols + column + 1
            current.append(data[index] if index < len(data) else None)
        matrix.append(current)
    return matrix
""",
    "runtime_error.py": """def make_matrix(data, rows, cols):
    return [[data[row * cols + column + len(data)] for column in range(cols)] for row in range(rows)]
""",
    "hardcoded_solution.py": """def make_matrix(data, rows, cols):
    if data == [1, 2, 3, 4, 5, 6]:
        return [[1, 2, 3], [4, 5, 6]]
    return []
""",
    "missing_function.py": """def transform_values(data):
    return list(data)
""",
}

RUBRICS = (
    ("structure", "Function & parameters", 3),
    ("approach", "2D list construction", 5),
    ("dimensions", "Correct dimensions", 4),
    ("values", "Value order & output", 6),
    ("quality", "Code quality", 2),
)

FIXTURES = (
    ("NONE", (3, 5, 4, 6, 2), 0.96, False),
    ("WRONG_ANSWER", (3, 5, 4, 0, 0), 0.78, False),
    ("RUNTIME_ERROR", (3, 4, 0, 0, 0), 0.86, False),
    ("WRONG_ANSWER", (3, 1, 1, 2, 1), 0.62, True),
    ("RUNTIME_ERROR", (0, 0, 0, 0, 1), 0.94, False),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _assignment(session: Session, provenance: DataProvenance) -> Assignment:
    assignment = Assignment(
        demo_key=DEMO_KEY,
        title="Matrix Transformation Assignment",
        description=(
            "Implement make_matrix(data, rows, cols) and return a row-major "
            "two-dimensional list with the requested dimensions."
        ),
        total_score=Decimal("20"),
        time_limit_ms=2_000,
        python_version="3.12",
        execution_mode=ExecutionMode.FUNCTION,
        entry_function="make_matrix",
        arguments_schema={
            "type": "object",
            "required": ["data", "rows", "cols"],
            "properties": {
                "data": {"type": "array"},
                "rows": {"type": "integer"},
                "cols": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        comparison_mode=ComparisonMode.JSON_VALUE,
        provenance=provenance,
    )
    session.add(assignment)
    session.flush()
    for index, (key, title, points) in enumerate(RUBRICS):
        session.add(
            RubricCriterion(
                assignment_id=assignment.id,
                criterion_key=key,
                title=title,
                description=f"Evaluate observable evidence for {title.lower()}.",
                max_score=Decimal(points),
                rules={
                    "evaluation_type": "hybrid" if key != "quality" else "static",
                    "required_evidence": ["test_or_runtime", "ast_or_static"],
                },
                sort_order=index,
                origin=RubricOrigin.HUMAN,
                approval_status=RubricStatus.HUMAN_APPROVED,
                approved_by="demo-instructor",
                approved_at=_now(),
            )
        )
    session.add_all(
        [
            TestCase(
                assignment_id=assignment.id,
                name="visible/basic-matrix",
                input_payload={"data": [1, 2, 3, 4, 5, 6], "rows": 2, "cols": 3},
                expected_output=[[1, 2, 3], [4, 5, 6]],
                comparison_mode=ComparisonMode.JSON_VALUE,
                is_hidden=False,
                sort_order=0,
            ),
            TestCase(
                assignment_id=assignment.id,
                name="hidden/edge-cases",
                input_payload={"data": [7, 8, 9, 10], "rows": 2, "cols": 2},
                expected_output=[[7, 8], [9, 10]],
                comparison_mode=ComparisonMode.JSON_VALUE,
                is_hidden=True,
                sort_order=1,
            ),
        ]
    )
    session.flush()
    return assignment


def _submissions(
    session: Session,
    assignment: Assignment,
    provenance: DataProvenance,
) -> list[Submission]:
    created: list[Submission] = []
    for index, (filename, content) in enumerate(SOURCES.items(), start=1):
        submission = Submission(
            assignment_id=assignment.id,
            student_reference=f"student-{index:02d}",
            source_version=1,
            status=SubmissionStatus.UPLOADED,
            provenance=provenance,
        )
        session.add(submission)
        session.flush()
        source = SourceFile(
            submission_id=submission.id,
            filename=filename,
            content=content,
            content_sha256=_hash(content),
            revision=1,
            is_current=True,
        )
        session.add(source)
        created.append(submission)
    session.flush()
    return created


def _queue_live(
    session: Session,
    assignment: Assignment,
    submissions: list[Submission],
) -> None:
    for submission in submissions:
        submission.status = SubmissionStatus.QUEUED
        session.add(
            ExecutionRun(
                submission_id=submission.id,
                status=ExecutionStatus.PENDING,
                runner_version="server-owned-pending",
                assignment_input_version=assignment.analysis_input_version,
                source_version=submission.source_version,
                provenance=DataProvenance.LIVE,
                run_metadata={
                    "job_type": "EXECUTION",
                    "requested_via": "DEMO_RESET_LIVE",
                    "auto_analyze": True,
                    "provenance": "PENDING",
                },
            )
        )


def _status_vector(filename: str, category: str) -> list[str]:
    if category == "NONE":
        return ["PASSED", "PASSED"]
    if filename == "hardcoded_solution.py":
        return ["PASSED", "WRONG_ANSWER"]
    if category == "WRONG_ANSWER":
        return ["WRONG_ANSWER", "WRONG_ANSWER"]
    return ["RUNTIME_ERROR", "RUNTIME_ERROR"]


def _fixture_evidence(
    session: Session,
    submission: Submission,
    run: ExecutionRun,
    source: SourceFile,
    tests: list[TestCase],
    statuses: list[str],
    category: str,
) -> list[Evidence]:
    missing = source.filename == "missing_function.py"
    ast = Evidence(
        submission_id=submission.id,
        execution_run_id=run.id,
        source_file_id=source.id,
        kind=EvidenceKind.AST_FINDING,
        visibility=EvidenceVisibility.STUDENT_VISIBLE,
        summary=(
            "No make_matrix function definition was found."
            if missing
            else "make_matrix(data, rows, cols) is defined with the expected parameters."
        ),
        details={"rule": "expected_function_exists", "passed": not missing},
        start_line=1,
        end_line=1,
        fingerprint=_hash(f"{submission.id}:ast"),
        provenance=DataProvenance.DEMO_FIXTURE,
    )
    session.add(ast)
    session.flush()
    evidence = [ast]
    for test, observed in zip(tests, statuses, strict=True):
        passed = observed == "PASSED"
        result = TestResult(
            execution_run_id=run.id,
            test_case_id=test.id,
            status=(
                TestResultStatus.PASSED
                if passed
                else TestResultStatus.ERROR
                if "ERROR" in observed
                else TestResultStatus.FAILED
            ),
            applied_comparison_mode=ComparisonMode.JSON_VALUE,
            actual_output=None if test.is_hidden else "fixture-observation",
            exit_code=0 if passed or observed == "WRONG_ANSWER" else 1,
            error_category=(
                None
                if passed
                else ErrorCategory.WRONG_ANSWER
                if observed == "WRONG_ANSWER"
                else ErrorCategory.RUNTIME_ERROR
            ),
            duration_ms=1.0,
            result_metadata={"fixture": True, "hidden_values_withheld": test.is_hidden},
        )
        session.add(result)
        session.flush()
        item = Evidence(
            submission_id=submission.id,
            execution_run_id=run.id,
            test_result_id=result.id,
            kind=EvidenceKind.TEST_RESULT,
            visibility=(
                EvidenceVisibility.REVIEWER_ONLY
                if test.is_hidden
                else EvidenceVisibility.STUDENT_VISIBLE
            ),
            summary=(
                "A hidden test produced fixture evidence; inputs and expected values are withheld."
                if test.is_hidden
                else f"Visible JSON_VALUE fixture observation: {observed}."
            ),
            details={
                "status": observed,
                "comparison_mode": ComparisonMode.JSON_VALUE.value,
                "hidden_values_withheld": test.is_hidden,
            },
            fingerprint=_hash(f"{submission.id}:{test.id}:{observed}"),
            provenance=DataProvenance.DEMO_FIXTURE,
        )
        session.add(item)
        session.flush()
        evidence.append(item)
    if category == "RUNTIME_ERROR":
        error = Evidence(
            submission_id=submission.id,
            execution_run_id=run.id,
            source_file_id=source.id,
            kind=EvidenceKind.EXECUTION_ERROR,
            visibility=EvidenceVisibility.STUDENT_VISIBLE,
            summary="IndexError was observed at a list access in the stored fixture.",
            details={"category": category, "exception_type": "IndexError"},
            start_line=2,
            end_line=2,
            fingerprint=_hash(f"{submission.id}:runtime"),
            provenance=DataProvenance.DEMO_FIXTURE,
        )
        session.add(error)
        session.flush()
        evidence.append(error)
    if source.filename == "hardcoded_solution.py":
        static = Evidence(
            submission_id=submission.id,
            execution_run_id=run.id,
            source_file_id=source.id,
            kind=EvidenceKind.STATIC_FINDING,
            visibility=EvidenceVisibility.STUDENT_VISIBLE,
            summary="A branch compares against a fixed example-sized literal list.",
            details={"rule": "large_literal_candidate"},
            start_line=2,
            end_line=3,
            fingerprint=_hash(f"{submission.id}:hardcoded"),
            provenance=DataProvenance.DEMO_FIXTURE,
        )
        session.add(static)
        session.flush()
        evidence.append(static)
    return evidence


def _fixture_analysis(
    session: Session,
    assignment: Assignment,
    submission: Submission,
    run: ExecutionRun,
    evidence: list[Evidence],
    criteria: list[RubricCriterion],
    scores: tuple[int, ...],
    confidence: float,
    category: str,
    stale: bool,
) -> AIAnalysis:
    visible_ids = [item.id for item in evidence if item.visibility == EvidenceVisibility.STUDENT_VISIBLE]
    analysis = AIAnalysis(
        submission_id=submission.id,
        execution_run_id=run.id,
        status=AnalysisStatus.STALE if stale else AnalysisStatus.COMPLETED,
        provider="fixture",
        model_name="fixture-no-provider-call",
        prompt_version="fixture-v1",
        summary=json.dumps(
            {
                "error_category": "LOGIC" if category == "WRONG_ANSWER" else category,
                "approach_summary": "The source shows evidence of an observable implementation approach.",
                "strengths": ["Only code and Primary Evidence observations are described."],
                "primary_issue": "Review the linked Primary Evidence.",
            },
            ensure_ascii=False,
        ),
        feedback=json.dumps(
            {
                "feedback_to_student": [
                    {
                        "concept": "Index mapping",
                        "shows_evidence_of": "The source shows evidence of constructing rows from columns.",
                        "likely_misconception": "The observed offset suggests a likely indexing misconception.",
                        "next_step": "Trace the first output element and verify that its source index is zero.",
                        "evidence_ids": visible_ids[:1],
                    }
                ],
                "uncertainties": ["This stored fixture is stale after a test change."] if stale else [],
            },
            ensure_ascii=False,
        ),
        model_reported_confidence=confidence,
        review_required=submission.student_reference != "student-01" or stale,
        review_reasons=["STALE_INPUT"] if stale else ([] if submission.student_reference == "student-01" else ["HUMAN_REVIEW"]),
        input_fingerprint=_hash(f"{submission.id}:fixture-analysis"),
        assignment_input_version=assignment.analysis_input_version,
        source_version=submission.source_version,
        external_data_manifest={"status": "NOT_SENT_FIXTURE", "fields_sent": []},
        stale_reason="A test changed after this stored fixture." if stale else None,
        completed_at=_now(),
        provenance=DataProvenance.DEMO_FIXTURE,
    )
    session.add(analysis)
    session.flush()
    for criterion, awarded in zip(criteria, scores, strict=True):
        score = RubricScore(
            analysis_id=analysis.id,
            rubric_criterion_id=criterion.id,
            suggested_score=Decimal(awarded),
            interpretation=(
                "The code shows evidence satisfying this criterion in the linked Primary Evidence."
                if Decimal(awarded) == criterion.max_score
                else "The linked execution and source observations suggest a gap in this criterion."
            ),
            model_reported_confidence=confidence,
        )
        score.primary_evidence = evidence[:2]
        session.add(score)
    return analysis


def _seed_fixtures(
    session: Session,
    assignment: Assignment,
    submissions: list[Submission],
) -> None:
    criteria = list(
        session.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.assignment_id == assignment.id)
            .order_by(RubricCriterion.sort_order)
        )
    )
    tests = list(
        session.scalars(
            select(TestCase)
            .where(TestCase.assignment_id == assignment.id)
            .order_by(TestCase.sort_order)
        )
    )
    for submission, fixture in zip(submissions, FIXTURES, strict=True):
        category, scores, confidence, stale = fixture
        source = session.scalar(
            select(SourceFile).where(SourceFile.submission_id == submission.id)
        )
        assert source is not None
        statuses = _status_vector(source.filename, category)
        run = ExecutionRun(
            submission_id=submission.id,
            status=ExecutionStatus.COMPLETED if category in {"NONE", "WRONG_ANSWER"} else ExecutionStatus.FAILED,
            runner_version="fixture-v1-not-executed",
            error_category=None if category == "NONE" else ErrorCategory(category),
            exception_type="IndexError" if category == "RUNTIME_ERROR" else None,
            signature_status="MISSING_FUNCTION" if source.filename == "missing_function.py" else "MATCHES",
            started_at=_now(),
            completed_at=_now(),
            assignment_input_version=assignment.analysis_input_version,
            source_version=submission.source_version,
            provenance=DataProvenance.DEMO_FIXTURE,
            run_metadata={
                "provenance": "DEMO_FIXTURE",
                "execution_available": False,
                "fixture_notice": "Stored demo fixture; Docker was not invoked.",
                "test_status_vector": statuses,
                "error_category": category,
                "exception_type": "IndexError" if category == "RUNTIME_ERROR" else None,
                "signature_status": "MISSING_FUNCTION" if source.filename == "missing_function.py" else "MATCHES",
                "ast_feature_summary": {
                    "syntax_valid": True,
                    "expected_function_exists": source.filename != "missing_function.py",
                    "signature_matches": source.filename != "missing_function.py",
                    "loop_present": source.filename not in {"missing_function.py", "hardcoded_solution.py"},
                },
            },
        )
        session.add(run)
        session.flush()
        evidence = _fixture_evidence(
            session, submission, run, source, tests, statuses, category
        )
        analysis = _fixture_analysis(
            session,
            assignment,
            submission,
            run,
            evidence,
            criteria,
            scores,
            confidence,
            category,
            stale,
        )
        if submission.student_reference == "student-01":
            review = HumanReview(
                submission_id=submission.id,
                ai_analysis_id=analysis.id,
                reviewer="demo-instructor",
                status=ReviewStatus.APPROVED,
                decision_reason="Fixture human review of linked evidence.",
                reviewed_assignment_version=assignment.analysis_input_version,
                reviewed_source_version=submission.source_version,
                is_current=True,
                approved_at=_now(),
            )
            review.scores = [
                HumanRubricScore(
                    rubric_criterion_id=criterion.id,
                    awarded_score=criterion.max_score,
                    reason="Fixture human approval.",
                )
                for criterion in criteria
            ]
            session.add(review)
            submission.status = SubmissionStatus.APPROVED
        else:
            submission.status = SubmissionStatus.REVIEW_REQUIRED
    session.flush()
    for index, submission in enumerate(submissions[1:3], start=1):
        run = session.scalar(
            select(ExecutionRun).where(ExecutionRun.submission_id == submission.id)
        )
        assert run is not None
        session.add(
            ConsistencyIssue(
                assignment_id=assignment.id,
                submission_id=submission.id,
                issue_type="DEMO_FIXTURE_POTENTIAL_ISSUE",
                severity=ConsistencyIssueSeverity.MEDIUM,
                potential_issue=True,
                description="Potential issue: compare linked evidence before confirming this score.",
                fingerprint_hash=_hash(f"demo-consistency-{index}"),
                test_status_vector=run.run_metadata["test_status_vector"],
                error_category=run.run_metadata["error_category"],
                ast_feature_summary=run.run_metadata["ast_feature_summary"],
                exception_type=run.exception_type,
                signature_status=run.signature_status,
            )
        )


def reset_demo(session: Session, *, live: bool) -> tuple[Assignment, list[Submission]]:
    existing = session.scalar(select(Assignment).where(Assignment.demo_key == DEMO_KEY))
    if existing is not None:
        session.delete(existing)
        session.flush()
    provenance = DataProvenance.STORED_LIVE if live else DataProvenance.DEMO_FIXTURE
    assignment = _assignment(session, provenance)
    submissions = _submissions(session, assignment, provenance)
    if live:
        _queue_live(session, assignment, submissions)
    else:
        _seed_fixtures(session, assignment, submissions)
    session.commit()
    return assignment, submissions
