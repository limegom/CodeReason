from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import ProviderUnavailableError
from app.config import Settings
from app.models import AnalysisStatus, ExecutionRun, ExecutionStatus, ReviewTrigger
from app.services.ai_orchestrator import (
    enqueue_analysis,
    enqueue_rubric_parse,
    process_analysis_job,
    process_rubric_parse_job,
)
from app.services.demo_seed import reset_demo


class FailingProvider:
    async def analyze(self, _payload: str):
        raise ProviderUnavailableError("provider request failed")

    async def parse_rubric(self, _payload: str):
        raise ProviderUnavailableError("provider request failed")


def _mark_execution_available(run: ExecutionRun) -> None:
    run.status = ExecutionStatus.COMPLETED
    run.run_metadata = {**run.run_metadata, "execution_available": True}


def test_missing_provider_configuration_is_recorded_as_not_sent(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ai_orchestrator.get_settings",
        lambda: Settings(openai_api_key=None),
    )
    _assignment, submissions = reset_demo(db_session, live=False)
    submission = submissions[0]
    run = db_session.scalar(
        select(ExecutionRun).where(ExecutionRun.submission_id == submission.id)
    )
    assert run is not None
    _mark_execution_available(run)
    job = enqueue_analysis(db_session, submission, execution_run_id=run.id)
    job.status = AnalysisStatus.RUNNING
    db_session.commit()

    failed = process_analysis_job(db_session, job.id)

    assert failed.status == AnalysisStatus.FAILED
    assert failed.external_data_manifest["status"] == "NOT_SENT_PROVIDER_UNAVAILABLE"
    assert "may_have_been_transmitted" not in failed.external_data_manifest
    assert failed.review_reasons == [ReviewTrigger.PROVIDER_UNAVAILABLE.value]


def test_failed_analysis_provider_attempt_is_not_reported_as_sent(
    db_session: Session,
) -> None:
    _assignment, submissions = reset_demo(db_session, live=False)
    submission = submissions[0]
    run = db_session.scalar(
        select(ExecutionRun).where(ExecutionRun.submission_id == submission.id)
    )
    assert run is not None
    _mark_execution_available(run)
    job = enqueue_analysis(db_session, submission, execution_run_id=run.id)
    job.status = AnalysisStatus.RUNNING
    db_session.commit()

    failed = process_analysis_job(db_session, job.id, provider=FailingProvider())

    assert failed.status == AnalysisStatus.FAILED
    assert failed.external_data_manifest["status"] == "TRANSMISSION_FAILED"
    assert failed.external_data_manifest["may_have_been_transmitted"] is True
    assert failed.review_reasons == [ReviewTrigger.PROVIDER_UNAVAILABLE.value]


def test_provider_and_execution_unavailability_remain_distinct_review_reasons(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ai_orchestrator.get_settings",
        lambda: Settings(openai_api_key=None),
    )
    _assignment, submissions = reset_demo(db_session, live=False)
    submission = submissions[0]
    run = db_session.scalar(
        select(ExecutionRun).where(ExecutionRun.submission_id == submission.id)
    )
    assert run is not None
    run.status = ExecutionStatus.UNAVAILABLE
    run.run_metadata = {**run.run_metadata, "execution_available": False}
    job = enqueue_analysis(db_session, submission, execution_run_id=run.id)
    job.status = AnalysisStatus.RUNNING
    db_session.commit()

    failed = process_analysis_job(db_session, job.id)

    assert failed.status == AnalysisStatus.FAILED
    assert failed.review_reasons == sorted(
        [
            ReviewTrigger.EXECUTION_UNAVAILABLE.value,
            ReviewTrigger.PROVIDER_UNAVAILABLE.value,
        ]
    )


def test_failed_rubric_provider_attempt_is_not_reported_as_sent(
    db_session: Session,
) -> None:
    assignment, _submissions = reset_demo(db_session, live=True)
    job = enqueue_rubric_parse(
        db_session,
        assignment,
        policy_text="Award points only for observable evidence.",
    )
    job.status = AnalysisStatus.RUNNING
    db_session.commit()

    failed = process_rubric_parse_job(
        db_session,
        job.id,
        provider=FailingProvider(),
    )

    assert failed.status == AnalysisStatus.FAILED
    assert failed.external_data_manifest["status"] == "TRANSMISSION_FAILED"
    assert failed.external_data_manifest["may_have_been_transmitted"] is True
