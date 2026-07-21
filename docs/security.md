# Security and privacy

## Trust model

Student source code, uploaded filenames, test inputs, and model output are untrusted. Docker is a defense-in-depth mechanism for the local MVP, not a production-grade security boundary. A production deployment should move execution to a separately administered, disposable compute environment with stronger kernel and tenant isolation.

The MVP is an unauthenticated, single-reviewer local application. Compose publishes the API and web services on loopback only. It must not be exposed to a classroom network or the public internet. `INTERNAL_WORKER_TOKEN` is a narrow guard for hidden worker-owned result-write adapters; it is not identity, session, RBAC, or tenant isolation.

## Upload controls

- Accept `.py` files only; ZIP uploads are rejected.
- Enforce a per-file byte limit and a per-batch file-count limit before persistence.
- Reject uploaded paths; retain only a validated `.py` basename plus generated database record IDs.
- Preserve source bytes immutably and never execute from a user-selected path.
- Do not log source bodies, authorization headers, API keys, or raw AI request payloads.

## Sandbox controls

The worker constructs every Docker argument from backend constants. User input cannot select the image, command, volume, environment, user, capability, or resource limit.

The fixed execution profile includes:

- no network
- non-root user
- read-only root filesystem and a bounded temporary filesystem
- dropped capabilities and `no-new-privileges`
- CPU, memory, process, wall-clock, and output limits
- no privileged mode
- no Docker socket or host bind mount inside the student container; `/input` is a backend-fixed Docker-managed anonymous volume
- no inherited host environment or secrets

Submission source is copied with `docker cp` into `/input` on a stopped, ephemeral container before execution. `/input` is a backend-fixed Docker-managed anonymous volume rather than a host bind mount, and assignment or student input cannot construct or configure the mount. The `finally` path makes up to three total `docker rm --force --volumes` attempts so successful removal also deletes the anonymous input volume, and a temporary-directory context removes the host-side staged file after success, timeout, cancellation, or failure. Docker-unavailable environments return an explicit unavailable result; CodeReason does not fabricate execution output.

Container cleanup is best effort. If the Docker CLI/daemon fails through all three bounded attempts, the container and its anonymous input volume can remain; the failure and generated container name are logged, but there is no separate orphan-container reaper. Operators must monitor Docker state and remove the orphan container and attached volume manually. Compose's `--remove-orphans` flag concerns Compose services and does not reconcile failed execution-container cleanup. Production use requires durable cleanup reconciliation in addition to a stronger execution boundary.

The worker itself may require Docker Engine access in a local demo. Access to the Docker socket is effectively host-privileged and is limited to the trusted worker service. The socket is never reachable from student code or the public API.

Public execute/analyze endpoints create only server-owned pending jobs. Execution results, Primary Evidence, and provider analysis are produced by the trusted worker. Internal compatibility mutation routes are omitted from OpenAPI and reject requests without `X-CodeReason-Internal` when `INTERNAL_WORKER_TOKEN` is configured.

## AI privacy boundary

The AI transmission pipeline scans and redacts:

- explicit identifiers supplied to the redactor (the worker supplies the current student reference)
- labelled English/Korean person-name assignments
- email addresses
- API keys, bearer tokens, private-key blocks, and common secret assignments

Redaction is best-effort and is not a data-loss-prevention guarantee. The review UI shows the server-recorded transmission status, field categories, redaction categories/count, and hidden-value/tool flags; it does not reveal the raw provider payload. Real student data should not be used in the bundled demo.

The current implementation applies pattern matching after the provider payload has been JSON-serialized. Escaped quotes can cause some generic assignments such as `api_key = "..."` or `access_token = "..."` to evade the assignment pattern. Keep live provider access disabled for real student code until redaction is applied field by field before serialization and regression tests cover these forms.

The transmission manifest is persisted before a provider call, changed to `TRANSMISSION_ATTEMPTED` immediately before the call, and finalized as `SENT`, `TRANSMISSION_FAILED`, or `NOT_SENT_PROVIDER_UNAVAILABLE`. A failed attempted call records that data may have been transmitted.

The model is not given tools and is told that source comments and strings are untrusted data, not instructions. Only Primary Evidence IDs already stored by the deterministic pipeline may support a deduction.

## Hidden tests and visibility

Hidden test inputs and expected outputs are `REVIEWER_ONLY`. Student feedback and CSV never serialize those fields. Reviewer API responses may include them only through an explicit reviewer view.

## Known limitations

- Docker shares the host kernel and is not sufficient isolation for hostile multi-tenant production workloads.
- Tests in the same execution run share one container and `/tmp`; student-created state can affect later tests.
- The local MVP has no login, RBAC, tenant boundary, CSRF protection, or rate limiting.
- Container removal has up to three total bounded attempts, but there is no durable cleanup queue or separate orphan reaper.
- Redaction may miss unlabeled personal names and secret formats outside its explicit identifiers and supported patterns.
- Generic quoted secret assignments may bypass the current post-serialization redaction pass.
- Background jobs do not yet use lease fencing, and not every provider or sandbox completion path rechecks its input versions.
- Historical test and rubric definitions are referenced rather than snapshotted, so later edits can change how an old result is displayed.
- Static detection of secrets, hardcoding, and dangerous behavior can have false positives and false negatives.
- Resource controls depend on Docker Engine and host platform support.
- Python 3.12 standard-library assignments are the only supported execution environment in the MVP.
