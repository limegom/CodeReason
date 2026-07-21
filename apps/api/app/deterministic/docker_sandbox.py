"""Docker execution with fixed arguments and copy-in source transfer.

This sandbox is defense in depth, not a production security boundary. The image,
entrypoint, command, capabilities, mounts, and environment are fixed here and
cannot be set by assignment or submission data.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from .execution import (
    ExecutionStatus,
    RawTestExecution,
    RunnerPhaseStatus,
    TestExecutionResult,
    classify_test_execution,
)
from .harness import (
    AssignmentExecutionConfig,
    HarnessValidationError,
    TestCaseSpec,
    build_runner_request,
    validate_source,
)


DOCKER_BINARY = "docker"
SANDBOX_IMAGE = "codereason-sandbox:py312"
SANDBOX_ENTRYPOINT = "/usr/local/bin/python"
SANDBOX_RUNNER = "/runner/runner.py"
CONTAINER_SOURCE = "/input/submission.py"
CONTAINER_INPUT_MOUNT = "type=volume,destination=/input,volume-nocopy"
RUNNER_STDIN_REQUEST_ARG = "--stdin-request"
MAX_DOCKER_OUTPUT_BYTES = 16 * 1024 * 1024
OVERALL_TIMEOUT_SECONDS = 60.0
DOCKER_CONTROL_TIMEOUT_SECONDS = 15.0
CONTAINER_CLEANUP_ATTEMPTS = 3
CONTAINER_CLEANUP_RETRY_DELAY_SECONDS = 0.25


logger = logging.getLogger("codereason.sandbox")


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class CommandRunner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        output_cap_bytes: int,
        input_data: bytes | None = None,
    ) -> ProcessOutcome: ...


class SubprocessCommandRunner:
    """Run without a shell and retain at most a fixed amount per output stream."""

    def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        output_cap_bytes: int,
        input_data: bytes | None = None,
    ) -> ProcessOutcome:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, never shell=True
            list(command),
            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        truncated = {"stdout": False, "stderr": False}

        def feed_stdin() -> None:
            try:
                if process.stdin is not None and input_data is not None:
                    process.stdin.write(input_data)
                    process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        def drain(stream: object, chunks: list[bytes], key: str) -> None:
            retained = 0
            while True:
                chunk = stream.read(8192)  # type: ignore[attr-defined]
                if not chunk:
                    return
                remaining = output_cap_bytes - retained
                if remaining > 0:
                    chunks.append(chunk[:remaining])
                    retained += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    truncated[key] = True

        stdout_thread = threading.Thread(
            target=drain, args=(process.stdout, stdout_chunks, "stdout"), daemon=True
        )
        stderr_thread = threading.Thread(
            target=drain, args=(process.stderr, stderr_chunks, "stderr"), daemon=True
        )
        stdin_thread = threading.Thread(target=feed_stdin, daemon=True)
        stdin_thread.start()
        stdout_thread.start()
        stderr_thread.start()
        timed_out = False
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            returncode = process.wait(timeout=5)
        finally:
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            stdin_thread.join(timeout=1)
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

        return ProcessOutcome(
            returncode=returncode,
            stdout=b"".join(stdout_chunks),
            stderr=b"".join(stderr_chunks),
            timed_out=timed_out,
            stdout_truncated=truncated["stdout"],
            stderr_truncated=truncated["stderr"],
        )


class DockerCommandBuilder:
    """Build only commands whose security-sensitive arguments are constants."""

    _CONTAINER_NAME = re.compile(r"^codereason-[0-9a-f]{32}$")

    @classmethod
    def _validate_name(cls, container_name: str) -> None:
        if not cls._CONTAINER_NAME.fullmatch(container_name):
            raise ValueError("container name was not generated by CodeReason")

    @staticmethod
    def availability() -> tuple[str, ...]:
        return (DOCKER_BINARY, "version", "--format", "{{.Server.Version}}")

    @classmethod
    def create(cls, container_name: str) -> tuple[str, ...]:
        cls._validate_name(container_name)
        return (
            DOCKER_BINARY,
            "create",
            "--name",
            container_name,
            "--network=none",
            "--read-only",
            "--user=65532:65532",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory=256m",
            "--memory-swap=256m",
            "--cpus=0.50",
            "--pids-limit=64",
            "--ulimit=nofile=64:64",
            "--ulimit=core=0:0",
            "--ipc=none",
            "--log-driver=none",
            f"--mount={CONTAINER_INPUT_MOUNT}",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16777216",
            "--workdir=/tmp",
            "--stop-timeout=1",
            "--init",
            "--interactive",
            "--pull=never",
            f"--entrypoint={SANDBOX_ENTRYPOINT}",
            SANDBOX_IMAGE,
            SANDBOX_RUNNER,
            RUNNER_STDIN_REQUEST_ARG,
        )

    @classmethod
    def copy_source(cls, local_path: Path, container_name: str) -> tuple[str, ...]:
        cls._validate_name(container_name)
        return (
            DOCKER_BINARY,
            "cp",
            str(local_path.resolve()),
            f"{container_name}:{CONTAINER_SOURCE}",
        )

    @classmethod
    def start(cls, container_name: str) -> tuple[str, ...]:
        cls._validate_name(container_name)
        return (DOCKER_BINARY, "start", "--attach", "--interactive", container_name)

    @classmethod
    def remove(cls, container_name: str) -> tuple[str, ...]:
        cls._validate_name(container_name)
        return (DOCKER_BINARY, "rm", "--force", "--volumes", container_name)


@dataclass(frozen=True, slots=True)
class SandboxRequest:
    source_code: str
    source_filename: str
    config: AssignmentExecutionConfig
    tests: tuple[TestCaseSpec, ...]
    per_test_timeout_ms: int = 2_000
    max_output_bytes: int = 65_536

    def __post_init__(self) -> None:
        validate_source(self.source_code, self.source_filename)
        object.__setattr__(self, "tests", tuple(self.tests))
        # Build once at validation time to reject invalid mode-specific inputs.
        build_runner_request(
            self.config,
            self.tests,
            per_test_timeout_ms=self.per_test_timeout_ms,
            max_output_bytes=self.max_output_bytes,
        )

    def runner_payload(self) -> dict[str, object]:
        return build_runner_request(
            self.config,
            self.tests,
            per_test_timeout_ms=self.per_test_timeout_ms,
            max_output_bytes=self.max_output_bytes,
        )


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    status: ExecutionStatus
    test_results: tuple[TestExecutionResult, ...] = ()
    unavailable_reason: str | None = None
    infrastructure_error: str | None = None

    @property
    def review_required(self) -> bool:
        return self.status in {
            ExecutionStatus.UNAVAILABLE,
            ExecutionStatus.INTERNAL_ERROR,
            ExecutionStatus.SECURITY_VIOLATION,
            ExecutionStatus.TIMEOUT,
        }


def _decode(value: bytes, limit: int = 2_000) -> str:
    return value.decode("utf-8", errors="replace")[:limit]


def _overall_status(results: Sequence[TestExecutionResult]) -> ExecutionStatus:
    priority = (
        ExecutionStatus.INTERNAL_ERROR,
        ExecutionStatus.SECURITY_VIOLATION,
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.SYNTAX_ERROR,
        ExecutionStatus.RUNTIME_ERROR,
        ExecutionStatus.WRONG_ANSWER,
        ExecutionStatus.PASSED,
    )
    observed = {result.status for result in results}
    return next(status for status in priority if status in observed)


class DockerSandbox:
    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or SubprocessCommandRunner()

    def _run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        output_cap_bytes: int = MAX_DOCKER_OUTPUT_BYTES,
        input_data: bytes | None = None,
    ) -> ProcessOutcome:
        return self._command_runner.run(
            command,
            timeout_seconds=timeout_seconds,
            output_cap_bytes=output_cap_bytes,
            input_data=input_data,
        )

    def _unavailable(self, reason: str) -> SandboxExecutionResult:
        # No per-test result is created because no execution occurred.
        return SandboxExecutionResult(
            status=ExecutionStatus.UNAVAILABLE,
            unavailable_reason=reason,
        )

    def _remove_container(self, container_name: str) -> bool:
        """Best-effort fixed-argv cleanup with bounded retries.

        Docker daemon failure can still prevent removal, so this is not a
        production-grade isolation guarantee.  A final failure is logged with
        the generated container name so an operator-side orphan reaper can act.
        """

        for _attempt in range(CONTAINER_CLEANUP_ATTEMPTS):
            try:
                outcome = self._run(
                    DockerCommandBuilder.remove(container_name),
                    timeout_seconds=DOCKER_CONTROL_TIMEOUT_SECONDS,
                    output_cap_bytes=4_096,
                )
            except (OSError, subprocess.SubprocessError):
                outcome = None
            if outcome is None:
                continue
            if not outcome.timed_out and outcome.returncode == 0:
                return True
            diagnostic = _decode(outcome.stderr).lower()
            if "no such container" in diagnostic:
                # A killed `docker create` client can race with daemon-side
                # completion. Retry the generated name before accepting that
                # there is nothing left to remove.
                if _attempt == CONTAINER_CLEANUP_ATTEMPTS - 1:
                    return True
                time.sleep(CONTAINER_CLEANUP_RETRY_DELAY_SECONDS)
        logger.error(
            "Sandbox container cleanup failed after retries",
            extra={"container_name": container_name},
        )
        return False

    def execute(self, request: SandboxRequest) -> SandboxExecutionResult:
        try:
            availability = self._run(
                DockerCommandBuilder.availability(),
                timeout_seconds=DOCKER_CONTROL_TIMEOUT_SECONDS,
                output_cap_bytes=4_096,
            )
        except (OSError, subprocess.SubprocessError):
            return self._unavailable("docker_cli_unavailable")
        if availability.timed_out or availability.returncode != 0:
            return self._unavailable("docker_daemon_unavailable")

        container_name = f"codereason-{uuid.uuid4().hex}"
        container_cleanup_required = False
        try:
            with tempfile.TemporaryDirectory(prefix="codereason-sandbox-") as temp_dir:
                staging = Path(temp_dir)
                source_path = staging / "submission.py"
                source_path.write_text(request.source_code, encoding="utf-8", newline="\n")
                try:
                    request_bytes = json.dumps(
                        request.runner_payload(),
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                except (TypeError, ValueError) as exc:
                    raise HarnessValidationError(
                        "test inputs and execution configuration must be JSON-compatible"
                    ) from exc

                # Mark cleanup before create. If the Docker client times out,
                # the daemon may still finish creating the named container.
                container_cleanup_required = True
                create = self._run(
                    DockerCommandBuilder.create(container_name),
                    timeout_seconds=DOCKER_CONTROL_TIMEOUT_SECONDS,
                )
                if create.timed_out:
                    return SandboxExecutionResult(
                        status=ExecutionStatus.INTERNAL_ERROR,
                        infrastructure_error="sandbox_container_create_timeout",
                    )
                if create.returncode != 0:
                    diagnostic = _decode(create.stderr).lower()
                    if any(
                        token in diagnostic
                        for token in (
                            "cannot connect",
                            "is the docker daemon running",
                            "no such image",
                            "pull access denied",
                        )
                    ):
                        return self._unavailable("sandbox_image_or_daemon_unavailable")
                    return SandboxExecutionResult(
                        status=ExecutionStatus.INTERNAL_ERROR,
                        infrastructure_error="sandbox_container_create_failed",
                    )
                copied = self._run(
                    DockerCommandBuilder.copy_source(source_path, container_name),
                    timeout_seconds=DOCKER_CONTROL_TIMEOUT_SECONDS,
                )
                if copied.returncode != 0:
                    return SandboxExecutionResult(
                        status=ExecutionStatus.INTERNAL_ERROR,
                        infrastructure_error="sandbox_copy_in_failed",
                    )

                started = self._run(
                    DockerCommandBuilder.start(container_name),
                    timeout_seconds=OVERALL_TIMEOUT_SECONDS,
                    input_data=request_bytes,
                )
                if started.timed_out:
                    return SandboxExecutionResult(
                        status=ExecutionStatus.TIMEOUT,
                        infrastructure_error="sandbox_overall_timeout",
                    )
                if started.stdout_truncated or started.stderr_truncated:
                    return SandboxExecutionResult(
                        status=ExecutionStatus.SECURITY_VIOLATION,
                        infrastructure_error="sandbox_report_output_limit_exceeded",
                    )
                if started.returncode != 0:
                    status = (
                        ExecutionStatus.SECURITY_VIOLATION
                        if started.returncode in {137, 143}
                        else ExecutionStatus.INTERNAL_ERROR
                    )
                    return SandboxExecutionResult(
                        status=status,
                        infrastructure_error="sandbox_runner_failed",
                    )

                try:
                    payload = json.loads(started.stdout.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return SandboxExecutionResult(
                        status=ExecutionStatus.INTERNAL_ERROR,
                        infrastructure_error="sandbox_runner_returned_invalid_json",
                    )
                return self._classify_payload(payload, request)
        except (OSError, subprocess.SubprocessError):
            return SandboxExecutionResult(
                status=ExecutionStatus.INTERNAL_ERROR,
                infrastructure_error="sandbox_command_failed",
            )
        finally:
            if container_cleanup_required:
                self._remove_container(container_name)

    def _classify_payload(
        self, payload: object, request: SandboxRequest
    ) -> SandboxExecutionResult:
        if not isinstance(payload, dict) or payload.get("version") != 1:
            return SandboxExecutionResult(
                status=ExecutionStatus.INTERNAL_ERROR,
                infrastructure_error="sandbox_runner_schema_mismatch",
            )
        raw_items = payload.get("results")
        if not isinstance(raw_items, list):
            return SandboxExecutionResult(
                status=ExecutionStatus.INTERNAL_ERROR,
                infrastructure_error="sandbox_runner_results_missing",
            )
        by_id: dict[str, dict[str, object]] = {}
        for item in raw_items:
            if not isinstance(item, dict) or not isinstance(item.get("test_case_id"), str):
                return SandboxExecutionResult(
                    status=ExecutionStatus.INTERNAL_ERROR,
                    infrastructure_error="sandbox_runner_result_invalid",
                )
            test_id = item["test_case_id"]
            if test_id in by_id:
                return SandboxExecutionResult(
                    status=ExecutionStatus.INTERNAL_ERROR,
                    infrastructure_error="sandbox_runner_duplicate_test_result",
                )
            by_id[test_id] = item
        if set(by_id) != {test.test_case_id for test in request.tests}:
            return SandboxExecutionResult(
                status=ExecutionStatus.INTERNAL_ERROR,
                infrastructure_error="sandbox_runner_incomplete_test_results",
            )

        results: list[TestExecutionResult] = []
        try:
            for test in request.tests:
                item = by_id[test.test_case_id]
                raw = RawTestExecution(
                    test_case_id=test.test_case_id,
                    phase_status=RunnerPhaseStatus(str(item.get("phase_status"))),
                    actual_output=str(item.get("actual_output", "")),
                    captured_stdout=str(item.get("captured_stdout", "")),
                    stderr=str(item.get("stderr", "")),
                    execution_time_ms=int(item.get("execution_time_ms", 0)),
                    exit_code=(
                        int(item["exit_code"])
                        if item.get("exit_code") is not None
                        else None
                    ),
                    exception_type=(
                        str(item["exception_type"])
                        if item.get("exception_type") is not None
                        else None
                    ),
                    error_message=(
                        str(item["error_message"])
                        if item.get("error_message") is not None
                        else None
                    ),
                    error_line=(
                        int(item["error_line"])
                        if item.get("error_line") is not None
                        else None
                    ),
                    output_truncated=bool(item.get("output_truncated", False)),
                )
                results.append(
                    classify_test_execution(
                        raw,
                        test,
                        request.config,
                        source_filename=request.source_filename,
                    )
                )
        except (TypeError, ValueError):
            return SandboxExecutionResult(
                status=ExecutionStatus.INTERNAL_ERROR,
                infrastructure_error="sandbox_runner_result_type_error",
            )
        return SandboxExecutionResult(
            status=_overall_status(results), test_results=tuple(results)
        )
