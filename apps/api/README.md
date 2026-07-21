# CodeReason API

FastAPI and SQLAlchemy backend for evidence-first programming assessment.

## Local development

Use Python 3.12 or newer from this directory:

    python -m pip install -e ".[dev]"
    alembic upgrade head
    uvicorn app.main:app --reload

The worker process has a stable entrypoint:

    python -m app.worker

`DATABASE_URL` defaults to `sqlite:///./codereason.db`. PostgreSQL URLs can be
supplied for Compose and production-like development.

## Domain invariants

- `Evidence` is limited to TestResult, ExecutionError, ASTFinding,
  StaticFinding, and SourceCodeLocation. AI interpretations remain derived data.
- AI-structured rubric criteria cannot be used for grading until a human changes
  their lifecycle state to `HUMAN_APPROVED`.
- Source, rubric, test, or execution-contract changes make prior analyses stale
  and reopen approved submissions without deleting review history.
- `final_total` is computed exclusively from a current approved HumanReview.
- Hidden-test inputs and expected answers are removed from student-facing views.
- The implemented local sandbox fixes its image, entrypoint, command, limits, and
  Docker arguments in backend code. It copies staged source with `docker cp` into
  `/input` on an ephemeral, stopped container. `/input` is a backend-fixed
  Docker-managed anonymous volume, not a host bind mount; assignment and student
  input cannot construct or configure mounts, commands, environments, or image
  names. Cleanup uses `docker rm --force --volumes` so successful container
  removal also removes the anonymous input volume. This is defense in depth for
  the local MVP, not a production-grade multi-tenant security boundary.
