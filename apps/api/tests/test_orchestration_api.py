from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.provider import ProviderResult
from app.ai.schemas import AIAnalysisOutput, RubricParseOutput
from app.config import Settings
from app.models import (
    AnalysisStatus,
    AIAnalysis,
    DataProvenance,
    Evidence,
    EvidenceVisibility,
    ExecutionRun,
    ExecutionStatus,
    RubricCriterion,
    RubricScore,
    RubricStatus,
    SourceFile,
)
from app.services.ai_orchestrator import (
    enqueue_analysis,
    enqueue_rubric_parse,
    process_analysis_job,
    process_rubric_parse_job,
)
from app.services.demo_seed import reset_demo


FAKE_OPENAI_KEY = "sk-" + "abcdefghijklmnopqrstuv"


def test_demo_reset_reviewer_read_model_and_csv_are_provenance_safe(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.demo.get_settings",
        lambda: Settings(demo_mode=True),
    )
    reset = client.post("/api/demo/reset", json={"provenance": "FIXTURE"})
    assert reset.status_code == 201
    payload = reset.json()
    assert payload["provenance"] == "DEMO_FIXTURE"
    assert len(payload["submission_ids"]) == 5
    assert payload["execution_jobs_queued"] == 0

    overviews = client.get("/api/reviewer/assignments")
    assert overviews.status_code == 200
    overview = overviews.json()[0]
    assert overview["submission_count"] == 5
    assert overview["pending_review_count"] == 4
    assert overview["approved_count"] == 1
    assert overview["rubric_ready"] is True

    bundles = client.get(
        f"/api/reviewer/assignments/{payload['assignment_id']}/submissions"
    )
    assert bundles.status_code == 200
    records = bundles.json()
    assert len(records) == 5
    assert all(record["submission"]["provenance"] == "DEMO_FIXTURE" for record in records)
    assert sum(record["final_grade"] is not None for record in records) == 1
    stale = next(
        record for record in records if record["source_file"]["filename"] == "hardcoded_solution.py"
    )
    assert stale["analysis"]["status"] == "STALE"
    assert stale["submission"]["status"] == "REVIEW_REQUIRED"
    hidden = [
        evidence
        for record in records
        for evidence in record["evidence"]
        if evidence["visibility"] == "REVIEWER_ONLY"
    ]
    assert hidden
    assert all("expected_output" not in evidence["details"] for evidence in hidden)
    hidden_results = [
        result
        for record in records
        for result in record["test_results"]
        if result["is_hidden"]
    ]
    assert hidden_results
    assert all(result["visibility"] == "REVIEWER_ONLY" for result in hidden_results)
    assert all("test_name" in result for result in hidden_results)
    assert all("input_payload" in result for result in hidden_results)
    assert all("expected_output" in result for result in hidden_results)

    exported = client.get(f"/api/assignments/{payload['assignment_id']}/export.csv")
    assert exported.status_code == 200
    assert exported.headers["x-codereason-hidden-test-values"] == "withheld"
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert rows[0]["final_total"] == "20.0"
    assert all(row["final_total"] == "" for row in rows[1:])
    assert "[7, 8, 9, 10]" not in exported.text


def test_reviewer_bundle_does_not_leak_internal_nested_score_evidence(
    db_session: Session,
    client: TestClient,
) -> None:
    _assignment, submissions = reset_demo(db_session, live=False)
    submission = submissions[1]
    analysis = db_session.scalar(
        select(AIAnalysis)
        .where(AIAnalysis.submission_id == submission.id)
        .options(
            selectinload(AIAnalysis.rubric_scores).selectinload(
                RubricScore.primary_evidence
            )
        )
    )
    assert analysis is not None
    score = next(item for item in analysis.rubric_scores if item.primary_evidence)
    internal_evidence = score.primary_evidence[0]
    internal_evidence.visibility = EvidenceVisibility.INTERNAL
    db_session.commit()

    response = client.get(f"/api/reviewer/submissions/{submission.id}")
    assert response.status_code == 200
    body = response.json()
    nested_ids = {
        evidence["id"]
        for rubric_score in body["analysis"]["rubric_scores"]
        for evidence in rubric_score["primary_evidence"]
    }
    assert internal_evidence.id not in nested_ids

    public_evidence = client.get(f"/api/submissions/{submission.id}/evidence")
    assert public_evidence.status_code == 200
    assert internal_evidence.id not in {item["id"] for item in public_evidence.json()}
    forbidden = client.get(
        f"/api/submissions/{submission.id}/evidence",
        params={"visibility": "INTERNAL"},
    )
    assert forbidden.status_code == 403
    public_analyses = client.get(f"/api/submissions/{submission.id}/analyses")
    assert public_analyses.status_code == 200
    nested_public_ids = {
        evidence["id"]
        for analysis_item in public_analyses.json()
        for rubric_score in analysis_item["rubric_scores"]
        for evidence in rubric_score["primary_evidence"]
    }
    assert internal_evidence.id not in nested_public_ids


def test_live_reset_queues_server_owned_execution_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.demo.get_settings",
        lambda: Settings(demo_mode=True),
    )
    response = client.post("/api/demo/reset", json={"provenance": "LIVE"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["provenance"] == "STORED_LIVE"
    assert payload["execution_jobs_queued"] == 5

    assignment_id = payload["assignment_id"]
    submissions = client.get(f"/api/assignments/{assignment_id}/submissions").json()
    assert all(submission["status"] == "QUEUED" for submission in submissions)
    for submission in submissions:
        runs = client.get(f"/api/submissions/{submission['id']}/execution-runs").json()
        assert len(runs) == 1
        assert runs[0]["status"] == "PENDING"
        assert runs[0]["run_metadata"]["auto_analyze"] is True


def test_execute_endpoint_owns_runner_and_input_snapshots(
    db_session: Session,
    client: TestClient,
) -> None:
    assignment, submissions = reset_demo(db_session, live=False)
    submission = submissions[1]
    response = client.post(
        f"/api/submissions/{submission.id}/execute",
        json={"analyze_after_execution": True},
    )
    assert response.status_code == 202
    run = response.json()
    assert run["runner_version"] == "server-owned-pending"
    assert run["assignment_input_version"] == assignment.analysis_input_version
    assert run["source_version"] == submission.source_version
    assert run["provenance"] == "LIVE"
    assert run["run_metadata"] == {
        "job_type": "EXECUTION",
        "requested_via": "API",
        "auto_analyze": True,
        "provenance": "PENDING",
    }


class FakeAnalysisProvider:
    def __init__(self, parsed) -> None:
        self.parsed = parsed
        self.payloads: list[str] = []

    async def analyze(self, payload: str) -> ProviderResult:
        self.payloads.append(payload)
        return ProviderResult(
            parsed=self.parsed,
            provider="openai",
            requested_model="gpt-5.6",
            resolved_model="gpt-5.6",
            response_id="resp_test",
            usage={"input_tokens": 1, "output_tokens": 1},
        )

    async def parse_rubric(self, policy_text: str) -> ProviderResult:
        self.payloads.append(policy_text)
        return ProviderResult(
            parsed=self.parsed,
            provider="openai",
            requested_model="gpt-5.6",
            resolved_model="gpt-5.6",
            response_id="resp_rubric",
            usage={},
        )


def test_analysis_orchestrator_redacts_and_persists_only_derived_analysis(
    db_session: Session,
) -> None:
    assignment, submissions = reset_demo(db_session, live=False)
    submission = submissions[3]
    source = db_session.scalar(
        select(SourceFile).where(SourceFile.submission_id == submission.id)
    )
    assert source is not None
    source.content += f"\n# student-04 jisu@example.edu {FAKE_OPENAI_KEY}\n"
    run = db_session.scalar(
        select(ExecutionRun).where(ExecutionRun.submission_id == submission.id)
    )
    evidence = list(
        db_session.scalars(
            select(Evidence).where(Evidence.execution_run_id == run.id)
        )
    )
    visible = next(item for item in evidence if item.visibility == EvidenceVisibility.STUDENT_VISIBLE)
    dynamic = next(item for item in evidence if item.kind.value == "TestResult")
    criteria = list(
        db_session.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.assignment_id == assignment.id)
            .order_by(RubricCriterion.sort_order)
        )
    )
    parsed = AIAnalysisOutput.model_validate(
        {
            "submission_summary": {
                "error_category": "LOGIC",
                "approach_summary": "The source shows evidence of a row-building approach.",
                "strengths": ["Observable loop structure is present."],
                "primary_issue": "Test output suggests an indexing defect.",
            },
            "rubric_results": [
                {
                    "rubric_id": criterion.id,
                    "max_score": float(criterion.max_score),
                    "suggested_score": float(criterion.max_score),
                    "model_reported_confidence": 0.9,
                    "reason": "The linked evidence shows an observable result.",
                    "evidence_ids": [visible.id, dynamic.id],
                    "manual_review_required": True,
                }
                for criterion in criteria
            ],
            "feedback_to_student": [
                {
                    "concept": "Indexing",
                    "shows_evidence_of": "The code shows evidence of nested traversal.",
                    "likely_misconception": "The offset suggests a likely indexing misconception.",
                    "next_step": "Trace the first element.",
                    "evidence_ids": [visible.id],
                }
            ],
            "uncertainties": [],
        }
    )
    provider = FakeAnalysisProvider(parsed)
    job = enqueue_analysis(db_session, submission, execution_run_id=run.id)
    job.status = AnalysisStatus.RUNNING
    db_session.commit()

    completed = process_analysis_job(db_session, job.id, provider=provider)

    assert completed.status == AnalysisStatus.COMPLETED
    assert completed.provenance == DataProvenance.LIVE
    assert completed.sanitized_input_hash
    assert completed.external_data_manifest["fields_sent"]
    sent = provider.payloads[0]
    assert "student-04" not in sent
    assert "jisu@example.edu" not in sent
    assert FAKE_OPENAI_KEY not in sent
    assert len(completed.rubric_scores) == len(criteria)
    assert "CONFLICTING_EVIDENCE" in completed.review_reasons
    evidence_count = db_session.query(Evidence).filter(Evidence.submission_id == submission.id).count()
    assert evidence_count == len(evidence)


def test_rubric_parse_job_redacts_and_creates_drafts(db_session: Session) -> None:
    assignment, _ = reset_demo(db_session, live=True)
    parsed = RubricParseOutput.model_validate(
        {
            "items": [
                {
                    "id": "reasoning structure",
                    "title": "Observable structure",
                    "description": "Combine runtime and source evidence.",
                    "max_score": 2,
                    "evaluation_type": "hybrid",
                    "required_evidence": ["test", "ast"],
                    "deduction_rules": [{"condition": "missing", "score": 0}],
                    "partial_credit_guidance": [
                        {"condition": "partial", "suggested_score_range": [0.5, 1.5]}
                    ],
                    "approval_status": "DRAFT",
                }
            ],
            "uncertainties": ["Instructor wording is ambiguous."],
        }
    )
    provider = FakeAnalysisProvider(parsed)
    job = enqueue_rubric_parse(
        db_session,
        assignment,
        policy_text=f"Contact jisu@example.edu and use {FAKE_OPENAI_KEY} for 2 points.",
    )
    job.status = AnalysisStatus.RUNNING
    db_session.commit()

    completed = process_rubric_parse_job(db_session, job.id, provider=provider)

    assert completed.status == AnalysisStatus.COMPLETED
    assert completed.provenance == DataProvenance.LIVE
    assert "jisu@example.edu" not in provider.payloads[0]
    assert FAKE_OPENAI_KEY not in provider.payloads[0]
    created = db_session.scalar(
        select(RubricCriterion).where(
            RubricCriterion.assignment_id == assignment.id,
            RubricCriterion.origin == "AI_STRUCTURED",
        )
    )
    assert created is not None
    assert created.approval_status == RubricStatus.DRAFT


def test_worker_owned_write_routes_are_not_in_public_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" not in paths["/api/submissions/{submission_id}/execution-runs"]
    assert "patch" not in paths["/api/submissions/{submission_id}/execution-runs/{run_id}"]
    assert "post" not in paths["/api/submissions/{submission_id}/analyses"]


def test_batch_upload_creates_one_immutable_submission_per_python_file(
    db_session: Session,
    client: TestClient,
) -> None:
    assignment, _ = reset_demo(db_session, live=True)
    response = client.post(
        f"/api/assignments/{assignment.id}/submissions/upload",
        data={"student_reference_prefix": "section-a"},
        files=[
            ("files", ("first.py", b"print('first')\n", "text/x-python")),
            ("files", ("second.py", b"print('second')\n", "text/x-python")),
        ],
    )
    assert response.status_code == 201
    created = response.json()
    assert all(item["provenance"] == "STORED_LIVE" for item in created)
    assert [item["student_reference"] for item in created] == [
        "section-a-01",
        "section-a-02",
    ]
    for item in created:
        sources = client.get(f"/api/submissions/{item['id']}/source-files").json()
        assert len(sources) == 1
        assert sources[0]["is_current"] is True
        assert sources[0]["revision"] == 1


def test_internal_token_blocks_client_authored_primary_evidence_writes(
    db_session: Session,
    client: TestClient,
    monkeypatch,
) -> None:
    _, submissions = reset_demo(db_session, live=True)
    monkeypatch.setattr(
        "app.api.dependencies.get_settings",
        lambda: Settings(internal_worker_token="worker-secret"),
    )
    response = client.post(
        f"/api/submissions/{submissions[0].id}/execution-runs",
        json={"runner_version": "client-spoof"},
    )
    assert response.status_code == 404
