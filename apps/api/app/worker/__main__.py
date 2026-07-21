from __future__ import annotations

import logging
import os
import signal
import threading

from sqlalchemy import select

from app.db import SessionLocal
from app.deterministic.docker_sandbox import DockerSandbox
from app.models import AIAnalysis, ExecutionRun
from app.services.ai_orchestrator import (
    enqueue_analysis,
    process_next_analysis,
    process_next_rubric_parse,
)
from app.services.execution_orchestrator import process_next_pending_execution


logger = logging.getLogger("codereason.worker")
shutdown = threading.Event()


def _stop(_signum: int, _frame: object) -> None:
    shutdown.set()


def process_once(*, sandbox: DockerSandbox | None = None) -> str | None:
    """Process at most one durable job, using a fresh database session."""

    with SessionLocal() as session:
        run_id = process_next_pending_execution(session, sandbox=sandbox)
        if run_id is not None:
            run = session.get(ExecutionRun, run_id)
            if run is not None and run.run_metadata.get("auto_analyze") is True:
                existing = session.scalar(
                    select(AIAnalysis.id).where(AIAnalysis.execution_run_id == run.id).limit(1)
                )
                if existing is None:
                    try:
                        enqueue_analysis(
                            session,
                            run.submission,
                            execution_run_id=run.id,
                        )
                    except ValueError:
                        logger.warning(
                            "Automatic analysis was not queued because its rubric/input gate failed",
                            extra={"execution_run_id": run.id},
                        )
            return run_id
        if process_next_rubric_parse(session):
            return "rubric-parse"
        if process_next_analysis(session):
            return "analysis"
        return None


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    interval = max(float(os.getenv("WORKER_POLL_SECONDS", "2")), 0.25)
    sandbox = DockerSandbox()
    logger.info("Worker started; polling durable execution and AI jobs")
    while not shutdown.is_set():
        try:
            run_id = process_once(sandbox=sandbox)
        except Exception:
            # A malformed job must not terminate the worker loop.
            logger.exception("Worker poll failed")
            run_id = None
        if run_id is not None:
            logger.info("Execution run processed", extra={"execution_run_id": run_id})
            continue
        shutdown.wait(interval)
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
