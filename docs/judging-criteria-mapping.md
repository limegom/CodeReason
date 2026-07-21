# Judging criteria mapping

## Impact

CodeReason addresses a repetitive, high-stakes education workflow: instructors must distinguish syntax, runtime, and logic failures while awarding explainable partial credit across many submissions. It reduces evidence collection and comparison work without delegating final grading authority to a model.

## Innovation

- Closed Primary Evidence taxonomy separated from Derived Analysis
- AST, static, test, execution-error, and source-location evidence combined under a human-approved rubric
- Versioned analysis with stale detection rather than silently reusing obsolete results
- Deterministic consistency fingerprints that raise potential issues without changing scores
- Explicit execution and comparison contracts recorded per result

## Use of OpenAI

The OpenAI Responses API is used in the worker for two bounded tasks:

1. turn natural-language grading policy into editable `DRAFT` rubric items;
2. create structured Derived Analysis and score suggestions that cite existing Primary Evidence IDs.

Structured output, application-level validation, best-effort redaction, conservative language, and mandatory human approval constrain both paths. Student code is treated as untrusted data rather than as prompt instructions.

## Technical quality

- Next.js and TypeScript frontend
- FastAPI, Pydantic, SQLAlchemy, and Alembic backend
- PostgreSQL with SQLite demo fallback
- fixed-argument Docker sandbox worker with best-effort cleanup
- deterministic unit tests, Docker integration tests, Vitest, Playwright, and CI
- immutable source rows, versioned analysis records, and preserved HumanReview rows; full snapshots of referenced grading definitions remain pre-release work

## Demo readiness

The bundled assignment contains five intentionally different submissions. A three-minute flow shows rubric approval, batch analysis, partial-credit evidence, runtime-versus-logic comparison, human override, consistency review, and CSV export.

## Responsible design

- AI output is advisory and labeled Derived Analysis.
- `model_reported_confidence` is not presented as calibrated probability.
- The product describes observable code evidence rather than claiming knowledge of student thought.
- The explicit student reference and common identifier or secret patterns receive best-effort redaction before external transfer; this is not a DLP guarantee.
- Hidden tests are restricted by evidence visibility.
- Docker is documented as an MVP defense-in-depth control, not a production-grade boundary.
- Provenance distinguishes live, stored-live, fixture, and unavailable results.
- The current deployment is explicitly limited to an unauthenticated, local single reviewer.
