"""Run one generated pytest file inside the RepoDoctor Docker sandbox."""

from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import TypedDict


SANDBOX_IMAGE = "repodoctor-sandbox"
SANDBOX_TIMEOUT_SECONDS = 10


class SandboxResult(TypedDict):
    passed: bool
    output: str
    timed_out: bool
    exit_code: int


def run_test(test_source: str) -> SandboxResult:
    """Run one generated test in a fresh, resource-constrained container."""
    with tempfile.TemporaryDirectory(prefix="repodoctor-") as temp_dir:
        Path(temp_dir).chmod(0o755)
        test_path = Path(temp_dir) / "test_generated.py"
        test_path.write_text(test_source, encoding="utf-8")
        test_path.chmod(0o444)

        container_name = f"repodoctor-test-{uuid.uuid4().hex}"
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
            "--cpus=1",
            "--memory=256m",
            "--pids-limit=64",
            "--env",
            "PYTHONPATH=/app",
            "--volume",
            f"{temp_dir}:/tests:ro",
            SANDBOX_IMAGE,
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "/tests/test_generated.py",
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=SANDBOX_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            _stop_container(container_name)
            return {
                "passed": False,
                "output": _combine_output(error.stdout, error.stderr),
                "timed_out": True,
                "exit_code": -1,
            }
        except OSError as error:
            return {"passed": False, "output": str(error), "timed_out": False, "exit_code": -1}

    return {
        "passed": completed.returncode == 0,
        "output": _combine_output(completed.stdout, completed.stderr),
        "timed_out": False,
        "exit_code": completed.returncode,
    }


def _stop_container(container_name: str) -> None:
    """Remove a timed-out container in case Docker did not stop it with its client."""
    subprocess.run(
        ["docker", "rm", "--force", container_name],
        capture_output=True,
        text=True,
        check=False,
    )


def _combine_output(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    def as_text(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return value or ""

    return as_text(stdout) + as_text(stderr)
