"""Trusted orchestration process inside the constrained Docker container."""

from __future__ import annotations

import json
import math
import os
import resource
import signal
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from security_policy import (  # type: ignore[import-not-found]
    MAX_REQUEST_BYTES,
    SOURCE_PATH,
    InvalidRunnerRequest,
    read_json_object,
    read_json_bytes,
    safe_error_message,
    validate_request,
)


RUNNER_PATH = Path("/runner/runner.py")
TEMP_ROOT = Path("/tmp")


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".new")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _validate_json_result(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"non-finite return value at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_result(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"non-string dictionary key at {path}")
            _validate_json_result(item, f"{path}.{key}")
        return
    raise TypeError(f"return value at {path} is not a JSON value")


def _serialize_function_result(value: Any, comparison_mode: str) -> str:
    if comparison_mode == "JSON_VALUE":
        _validate_json_result(value)
    elif isinstance(value, str):
        return value
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _student_line(exc: BaseException) -> int | None:
    if isinstance(exc, SyntaxError):
        return exc.lineno
    frames = traceback.extract_tb(exc.__traceback__)
    for frame in reversed(frames):
        if Path(frame.filename).name == "submission.py":
            return frame.lineno
    return None


def _child(task_path: Path, outcome_path: Path) -> int:
    try:
        task = read_json_object(task_path, MAX_REQUEST_BYTES)
        source = SOURCE_PATH.read_text(encoding="utf-8")
        compiled = compile(source, "submission.py", "exec", dont_inherit=True)
        namespace: dict[str, Any] = {
            "__builtins__": __builtins__,
            "__file__": "submission.py",
            "__name__": (
                "student_submission"
                if task["mode"] == "FUNCTION"
                else "__main__"
            ),
        }
        exec(compiled, namespace, namespace)
        if task["mode"] == "FUNCTION":
            entry = namespace.get(task["entry_function"])
            if not callable(entry):
                raise LookupError(
                    f"required function {task['entry_function']!r} is not callable"
                )
            arguments = task["input"]
            result = entry(*arguments["args"], **arguments["kwargs"])
            actual_output = _serialize_function_result(result, task["comparison_mode"])
        else:
            actual_output = ""
        _write_json(
            outcome_path,
            {"phase_status": "COMPLETED", "actual_output": actual_output},
        )
        return 0
    except SyntaxError as exc:
        _write_json(
            outcome_path,
            {
                "phase_status": "SYNTAX_ERROR",
                "exception_type": "SyntaxError",
                "error_message": safe_error_message(exc.msg),
                "error_line": exc.lineno,
            },
        )
        return 2
    except BaseException as exc:  # student exceptions, including SystemExit
        try:
            _write_json(
                outcome_path,
                {
                    "phase_status": "RUNTIME_ERROR",
                    "exception_type": type(exc).__name__,
                    "error_message": safe_error_message(exc),
                    "error_line": _student_line(exc),
                },
            )
        except BaseException:
            return 3
        return 1


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()


def _apply_child_resource_limits(max_output_bytes: int) -> None:
    # One byte beyond the policy cap lets the parent distinguish a limit hit
    # from a legitimate output whose size is exactly the allowed maximum.
    resource.setrlimit(
        resource.RLIMIT_FSIZE,
        (max_output_bytes + 1, max_output_bytes + 1),
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _read_limited(path: Path, max_bytes: int) -> tuple[str, bool]:
    if not path.exists():
        return "", False
    size = path.stat().st_size
    with path.open("rb") as stream:
        value = stream.read(max_bytes)
    return value.decode("utf-8", errors="replace"), size > max_bytes


def _run_one_test(
    execution: dict[str, Any],
    test: dict[str, Any],
    *,
    timeout_ms: int,
    max_output_bytes: int,
) -> dict[str, Any]:
    token = uuid.uuid4().hex
    task_path = TEMP_ROOT / f"codereason-task-{token}.json"
    outcome_path = TEMP_ROOT / f"codereason-outcome-{token}.json"
    stdout_path = TEMP_ROOT / f"codereason-stdout-{token}.txt"
    stderr_path = TEMP_ROOT / f"codereason-stderr-{token}.txt"
    paths = (task_path, outcome_path, stdout_path, stderr_path)
    started_at = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    try:
        _write_json(
            task_path,
            {
                "mode": execution["mode"],
                "entry_function": execution.get("entry_function"),
                "input": test["input"],
                "comparison_mode": test["comparison_mode"],
            },
        )
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--child",
                    str(task_path),
                    str(outcome_path),
                ],
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
                close_fds=True,
                preexec_fn=lambda: _apply_child_resource_limits(max_output_bytes),
            )
            stdin_value = (
                test["input"].encode("utf-8")
                if execution["mode"] == "STDIN_STDOUT"
                else b""
            )

            def feed_stdin() -> None:
                try:
                    if process and process.stdin:
                        process.stdin.write(stdin_value)
                        process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

            import threading

            feeder = threading.Thread(target=feed_stdin, daemon=True)
            feeder.start()
            deadline = started_at + timeout_ms / 1_000
            exceeded = False
            timed_out = False
            while process.poll() is None:
                if (
                    stdout_path.stat().st_size > max_output_bytes
                    or stderr_path.stat().st_size > max_output_bytes
                ):
                    exceeded = True
                    _kill_process_group(process)
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    _kill_process_group(process)
                    break
                time.sleep(0.01)
            process.wait(timeout=2)
            feeder.join(timeout=0.1)

        stdout, stdout_truncated = _read_limited(stdout_path, max_output_bytes)
        stderr, stderr_truncated = _read_limited(stderr_path, max_output_bytes)
        elapsed_ms = round((time.monotonic() - started_at) * 1_000)
        common = {
            "test_case_id": test["test_case_id"],
            "stderr": stderr,
            "execution_time_ms": elapsed_ms,
            "exit_code": process.returncode,
            "output_truncated": exceeded or stdout_truncated or stderr_truncated,
        }
        if exceeded or stdout_truncated or stderr_truncated:
            return {
                **common,
                "phase_status": "SECURITY_VIOLATION",
                "actual_output": stdout,
                "error_message": "stdout or stderr exceeded the configured limit",
            }
        if timed_out:
            return {
                **common,
                "phase_status": "TIMEOUT",
                "actual_output": stdout,
                "error_message": "execution exceeded the per-test timeout",
            }
        if not outcome_path.exists():
            return {
                **common,
                "phase_status": "RUNTIME_ERROR",
                "actual_output": stdout,
                "exception_type": "ProcessExited",
                "error_message": "student process exited before reporting a result",
            }
        outcome = read_json_object(outcome_path, MAX_REQUEST_BYTES)
        if execution["mode"] == "STDIN_STDOUT" and outcome.get("phase_status") == "COMPLETED":
            outcome["actual_output"] = stdout
        else:
            outcome["captured_stdout"] = stdout
        return {**common, **outcome}
    finally:
        if process and process.poll() is None:
            _kill_process_group(process)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        for path in paths:
            try:
                path.unlink(missing_ok=True)
                path.with_suffix(".new").unlink(missing_ok=True)
            except OSError:
                pass


def _parent_from_stdin() -> int:
    try:
        request_bytes = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        request = validate_request(read_json_bytes(request_bytes, MAX_REQUEST_BYTES))
        execution = request["execution"]
        limits = request["limits"]
        results = [
            _run_one_test(
                execution,
                test,
                timeout_ms=limits["per_test_timeout_ms"],
                max_output_bytes=limits["max_output_bytes"],
            )
            for test in request["tests"]
        ]
        sys.stdout.write(
            json.dumps(
                {"version": 1, "results": results},
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        )
        return 0
    except (InvalidRunnerRequest, OSError, ValueError, TypeError) as exc:
        sys.stderr.write(safe_error_message(exc))
        return 64


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        return _child(Path(sys.argv[2]), Path(sys.argv[3]))
    if len(sys.argv) == 2 and sys.argv[1] == "--stdin-request":
        return _parent_from_stdin()
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
