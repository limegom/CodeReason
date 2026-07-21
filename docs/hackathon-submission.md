# CodeReason project overview

## Tagline

Evidence-based AI grading that explains what student code demonstrates, where execution fails, and why every partial-credit suggestion needs human approval.

## Problem

Programming instructors often see the same wrong output produced by very different implementations. Output-only grading misses useful structure, manual evidence collection is slow, and unconstrained AI grading can invent confident-looking justifications. Graders also need a practical way to check whether the same rubric was applied consistently across a cohort.

## Solution

CodeReason runs Python submissions in a restricted local Docker sandbox, gathers test and source-structure evidence, then uses the OpenAI Responses API for rubric-bound Derived Analysis. Every suggested deduction must cite existing Primary Evidence. Instructors inspect the code and evidence, edit or approve scores, review potential consistency issues, and export AI suggestions separately. `final_total` remains blank until human approval.

## Key differentiators

- Primary Evidence and AI interpretation are different data classes and UI surfaces.
- AI-created rubrics cannot grade until a human approves them.
- Changes to source, tests, or rubric make old analysis stale.
- Hidden-test visibility follows data from storage through feedback and export.
- Consistency checking compares deterministic behavior fingerprints and only raises potential issues.
- Student code passes through best-effort identifier and secret redaction before an external request and is treated as untrusted prompt data.
- Assignment, submission, execution, evidence, and analysis records preserve `LIVE`, `STORED_LIVE`, `DEMO_FIXTURE`, or `UNAVAILABLE` provenance.

## OpenAI integration

The FastAPI worker uses the OpenAI Responses API with Pydantic-validated Structured Outputs. The configured model, prompt version, response metadata, and analysis time are recorded. Application code independently validates rubric IDs, score bounds, evidence references, missing evidence, conflicting deterministic observations, execution availability, and review-required conditions. The default model is configurable through `OPENAI_MODEL`.

## Human-in-the-loop principle

AI scores are suggestions. `final_total` is unavailable—and remains blank in CSV—until a person approves a review. Later input changes preserve prior review rows but invalidate them as the current grade. Complete immutable snapshots of the referenced test and rubric definitions remain pre-release work.

## Built with

Next.js, TypeScript, Tailwind CSS, TanStack Query, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, SQLite, Docker, OpenAI API, pytest, Vitest, Playwright, and GitHub Actions.

## Demo

The bundled Matrix Transformation Assignment includes correct, wrong-index, runtime-error, hardcoded, and missing-function submissions. See [demo-script.md](demo-script.md) for the three-minute presentation.

## Limitations

The MVP supports Python 3.12 standard-library assignments only. It is an unauthenticated, local single-reviewer application. Docker is a local demo defense-in-depth mechanism, not a production multi-tenant security boundary. Secret and identifier detection, as well as hardcoding analysis, are heuristic. Live provider verification is pending privacy and versioning hardening. Authentication, LMS integration, plagiarism detection, and automatic grade publication are intentionally out of scope.
