from __future__ import annotations

import shutil
import subprocess

import pytest

from app.deterministic.comparison import ComparisonMode
from app.deterministic.docker_sandbox import SANDBOX_IMAGE, DockerSandbox, SandboxRequest
from app.deterministic.execution import ExecutionStatus
from app.deterministic.harness import AssignmentExecutionConfig, ExecutionMode, TestCaseSpec


@pytest.fixture(scope="module", autouse=True)
def require_built_sandbox_image():
    if not shutil.which("docker"):
        pytest.skip("Docker CLI is unavailable")
    daemon = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        check=False,
        timeout=20,
    )
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is unavailable")
    image = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        capture_output=True,
        check=False,
        timeout=20,
    )
    if image.returncode != 0:
        pytest.skip(f"sandbox image {SANDBOX_IMAGE} is not built")


def _execute(source: str, expected: str):
    request = SandboxRequest(
        source_code=source,
        source_filename="submission.py",
        config=AssignmentExecutionConfig(
            execution_mode=ExecutionMode.STDIN_STDOUT,
            comparison_mode=ComparisonMode.IGNORE_FINAL_NEWLINE,
        ),
        tests=(TestCaseSpec("integration", "", expected),),
        per_test_timeout_ms=2_000,
    )
    return DockerSandbox().execute(request)


def test_container_root_filesystem_is_read_only():
    result = _execute(
        """\
try:
    open('/codereason-write-test', 'w').write('not allowed')
except OSError:
    print('blocked')
else:
    print('writable')
""",
        "blocked",
    )

    assert result.status is ExecutionStatus.PASSED


def test_container_network_is_disabled():
    result = _execute(
        """\
import socket
try:
    socket.create_connection(('203.0.113.1', 80), timeout=0.25)
except OSError:
    print('blocked')
else:
    print('connected')
""",
        "blocked",
    )

    assert result.status is ExecutionStatus.PASSED


def test_copied_source_is_not_writable_by_student_code():
    result = _execute(
        """\
try:
    open('/input/submission.py', 'w').write('changed')
except OSError:
    print('blocked')
else:
    print('writable')
""",
        "blocked",
    )

    assert result.status is ExecutionStatus.PASSED


def test_host_environment_is_not_forwarded(monkeypatch):
    monkeypatch.setenv("CODEREASON_HOST_ONLY_SECRET", "must-not-enter-container")
    result = _execute(
        """\
import os
print(os.environ.get('CODEREASON_HOST_ONLY_SECRET', 'absent'))
""",
        "absent",
    )

    assert result.status is ExecutionStatus.PASSED


def test_function_mode_invokes_fixed_entry_and_compares_json_value():
    request = SandboxRequest(
        source_code="""\
def make_matrix(data, rows, cols):
    return [data[index:index + cols] for index in range(0, rows * cols, cols)]
""",
        source_filename="submission.py",
        config=AssignmentExecutionConfig(
            execution_mode=ExecutionMode.FUNCTION,
            entry_function="make_matrix",
            arguments_schema={
                "type": "object",
                "properties": {
                    "args": {"type": "array", "minItems": 3, "maxItems": 3},
                    "kwargs": {"type": "object"},
                },
            },
            comparison_mode=ComparisonMode.JSON_VALUE,
        ),
        tests=(
            TestCaseSpec(
                "function-integration",
                {"args": [[1, 2, 3, 4], 2, 2], "kwargs": {}},
                [[1, 2], [3, 4]],
            ),
        ),
    )

    result = DockerSandbox().execute(request)

    assert result.status is ExecutionStatus.PASSED
    assert result.test_results[0].comparison_mode is ComparisonMode.JSON_VALUE
