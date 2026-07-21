from __future__ import annotations

import json
import sys
from pathlib import Path

from app.deterministic.comparison import ComparisonMode
from app.deterministic.docker_sandbox import (
    CONTAINER_INPUT_MOUNT,
    CONTAINER_SOURCE,
    RUNNER_STDIN_REQUEST_ARG,
    SANDBOX_IMAGE,
    SANDBOX_RUNNER,
    DockerCommandBuilder,
    DockerSandbox,
    ProcessOutcome,
    SandboxRequest,
    SubprocessCommandRunner,
)
from app.deterministic.execution import ExecutionStatus
from app.deterministic.harness import AssignmentExecutionConfig, ExecutionMode, TestCaseSpec


def _container_name():
    return "codereason-" + "a" * 32


def test_create_command_has_fixed_security_invariants_and_no_bind_or_env_inputs():
    command = DockerCommandBuilder.create(_container_name())

    assert "--network=none" in command
    assert "--read-only" in command
    assert "--user=65532:65532" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges:true" in command
    assert "--pids-limit=64" in command
    assert "--ulimit=core=0:0" in command
    assert "--log-driver=none" in command
    assert "--pull=never" in command
    assert any(token.startswith("--tmpfs=/tmp:") for token in command)
    assert [token for token in command if token.startswith("--mount=")] == [
        f"--mount={CONTAINER_INPUT_MOUNT}"
    ]
    assert "type=volume" in CONTAINER_INPUT_MOUNT
    assert "destination=/input" in CONTAINER_INPUT_MOUNT
    assert "source=" not in CONTAINER_INPUT_MOUNT
    assert command[-3:] == (SANDBOX_IMAGE, SANDBOX_RUNNER, RUNNER_STDIN_REQUEST_ARG)
    assert "--interactive" in command
    assert not any(
        token == "-v"
        or token.startswith("--volume")
        or token.startswith("--mount=type=bind")
        or token.startswith("--env")
        or token == "--privileged"
        for token in command
    )


def test_container_name_cannot_be_injected():
    import pytest

    with pytest.raises(ValueError):
        DockerCommandBuilder.create("student-name --privileged")


def test_copy_in_uses_docker_cp_to_fixed_source_path(tmp_path):
    source = tmp_path / "submission.py"
    source.write_text("pass", encoding="utf-8")

    source_command = DockerCommandBuilder.copy_source(source, _container_name())

    assert source_command[1] == "cp"
    assert source_command[-1].endswith(f":{CONTAINER_SOURCE}")


class FakeCommandRunner:
    def __init__(
        self,
        start_outcome: ProcessOutcome | None = None,
        unavailable=False,
        copy_fails=False,
        start_raises=False,
        create_times_out=False,
        remove_failures=0,
    ):
        self.calls: list[tuple[str, ...]] = []
        self.copied_local_paths: list[Path] = []
        self.unavailable = unavailable
        self.copy_fails = copy_fails
        self.start_raises = start_raises
        self.create_times_out = create_times_out
        self.remove_failures = remove_failures
        self.start_input: bytes | None = None
        self.start_outcome = start_outcome or ProcessOutcome(
            returncode=0,
            stdout=json.dumps(
                {
                    "version": 1,
                    "results": [
                        {
                            "test_case_id": "case-1",
                            "phase_status": "COMPLETED",
                            "actual_output": "ok",
                            "execution_time_ms": 2,
                            "exit_code": 0,
                        }
                    ],
                }
            ).encode(),
        )

    def run(self, command, *, timeout_seconds, output_cap_bytes, input_data=None):
        command = tuple(command)
        self.calls.append(command)
        action = command[1]
        if action == "version":
            return ProcessOutcome(returncode=1 if self.unavailable else 0)
        if action == "create" and self.create_times_out:
            return ProcessOutcome(returncode=-1, timed_out=True)
        if action == "cp":
            self.copied_local_paths.append(Path(command[2]))
            return ProcessOutcome(returncode=1 if self.copy_fails else 0)
        if action == "start":
            if self.start_raises:
                raise OSError("docker client disappeared")
            self.start_input = input_data
            return self.start_outcome
        if action == "rm" and self.remove_failures > 0:
            self.remove_failures -= 1
            return ProcessOutcome(returncode=1)
        return ProcessOutcome(returncode=0)


def _request():
    return SandboxRequest(
        source_code="print('ok')\n",
        source_filename="submission.py",
        config=AssignmentExecutionConfig(
            ExecutionMode.STDIN_STDOUT,
            ComparisonMode.EXACT,
        ),
        tests=(TestCaseSpec("case-1", "", "ok"),),
    )


def test_success_copies_then_starts_and_always_removes_temp_and_container():
    runner = FakeCommandRunner()
    result = DockerSandbox(runner).execute(_request())

    actions = [command[1] for command in runner.calls]
    assert actions == ["version", "create", "cp", "start", "rm"]
    assert runner.start_input is not None
    assert json.loads(runner.start_input)["tests"][0]["test_case_id"] == "case-1"
    assert "expected_output" not in runner.start_input.decode("utf-8")
    assert result.status is ExecutionStatus.PASSED
    assert result.test_results[0].comparison_mode is ComparisonMode.EXACT
    assert all(not path.exists() for path in runner.copied_local_paths)


def test_timeout_still_forces_container_removal_without_fake_test_results():
    runner = FakeCommandRunner(
        ProcessOutcome(returncode=-1, timed_out=True)
    )
    result = DockerSandbox(runner).execute(_request())

    assert result.status is ExecutionStatus.TIMEOUT
    assert result.test_results == ()
    assert runner.calls[-1][1:4] == ("rm", "--force", "--volumes")


def test_create_timeout_still_removes_a_possible_late_daemon_container():
    runner = FakeCommandRunner(create_times_out=True)

    result = DockerSandbox(runner).execute(_request())

    assert result.status is ExecutionStatus.INTERNAL_ERROR
    assert result.infrastructure_error == "sandbox_container_create_timeout"
    assert [command[1] for command in runner.calls] == ["version", "create", "rm"]
    assert runner.calls[-1][1:4] == ("rm", "--force", "--volumes")


def test_container_removal_retries_with_the_same_fixed_argv_after_failures():
    runner = FakeCommandRunner(remove_failures=2)

    result = DockerSandbox(runner).execute(_request())

    remove_calls = [command for command in runner.calls if command[1] == "rm"]
    assert result.status is ExecutionStatus.PASSED
    assert len(remove_calls) == 3
    assert len(set(remove_calls)) == 1
    assert remove_calls[0][1:4] == ("rm", "--force", "--volumes")


def test_copy_error_still_removes_container_and_host_temporary_source():
    runner = FakeCommandRunner(copy_fails=True)
    result = DockerSandbox(runner).execute(_request())

    assert result.status is ExecutionStatus.INTERNAL_ERROR
    assert [command[1] for command in runner.calls][-1] == "rm"
    assert all(not path.exists() for path in runner.copied_local_paths)


def test_command_error_after_create_is_classified_and_container_is_removed():
    runner = FakeCommandRunner(start_raises=True)
    result = DockerSandbox(runner).execute(_request())

    assert result.status is ExecutionStatus.INTERNAL_ERROR
    assert result.infrastructure_error == "sandbox_command_failed"
    assert runner.calls[-1][1] == "rm"


def test_docker_unavailable_is_explicit_and_does_not_create_results():
    runner = FakeCommandRunner(unavailable=True)
    result = DockerSandbox(runner).execute(_request())

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.unavailable_reason == "docker_daemon_unavailable"
    assert result.test_results == ()
    assert [command[1] for command in runner.calls] == ["version"]


def test_host_command_capture_discards_bytes_beyond_fixed_cap():
    outcome = SubprocessCommandRunner().run(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 4096)"],
        timeout_seconds=5,
        output_cap_bytes=64,
    )

    assert outcome.returncode == 0
    assert len(outcome.stdout) == 64
    assert outcome.stdout_truncated is True
