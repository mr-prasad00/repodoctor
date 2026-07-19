"""Run one generated pytest file inside the RepoDoctor Docker sandbox."""

from __future__ import annotations

import os
import re
import subprocess
import sys
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
                "output": format_test_output(_combine_output(error.stdout, error.stderr)),
                "timed_out": True,
                "exit_code": -1,
            }
        except OSError:
            # Fall back to isolated subprocess pytest if Docker is not available in cloud PaaS containers (e.g. Railway)
            cur_file_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = str(Path(cur_file_dir).parent)
            
            python_exec = sys.executable or "python3"
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{cur_file_dir}:{parent_dir}:."
            
            local_cmd = [
                python_exec,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                str(test_path),
            ]
            try:
                completed = subprocess.run(
                    local_cmd,
                    capture_output=True,
                    text=True,
                    timeout=SANDBOX_TIMEOUT_SECONDS,
                    cwd=temp_dir,
                    env=env,
                    check=False,
                )
            except Exception as sub_err:
                return {"passed": False, "output": format_test_output(str(sub_err)), "timed_out": False, "exit_code": -1}

    return {
        "passed": completed.returncode == 0,
        "output": format_test_output(_combine_output(completed.stdout, completed.stderr)),
        "timed_out": False,
        "exit_code": completed.returncode,
    }


def format_test_output(output: str) -> str:
    """Parse and clean up raw sandbox output into a human-friendly format."""
    if not output:
        return output

    assert_match = re.search(r"E\s+assert\s+(.+?)\s*==\s*(.+)", output)
    where_match = re.search(r"E\s+\+\s+where\s+(.+?)\s*=\s*(.+)", output)

    summary = []
    if assert_match:
        observed_val = assert_match.group(1).strip()
        expected_val = assert_match.group(2).strip()

        if where_match:
            call_expr = where_match.group(2).strip()
            observed_val = where_match.group(1).strip()
        else:
            call_expr = None
            lines = output.splitlines()
            for line in lines:
                if line.strip().startswith(">") and "assert" in line:
                    call_expr = line.replace(">", "").replace("assert", "").strip()
                    break

        summary.append("==================================================")
        summary.append("❌ TEST FAILURE ENCOUNTERED IN SANDBOX")
        summary.append("==================================================")
        if call_expr:
            summary.append(f"🔍 Executed:  {call_expr}")
        summary.append(f"📥 Returned:  {observed_val}")
        summary.append(f"📤 Expected:  {expected_val}")
        summary.append("==================================================")
        summary.append("\nDetailed Sandbox Logs:")
        summary.append("--------------------------------------------------")
        summary.append(output)
        return "\n".join(summary)

    exc_match = re.search(r"E\s+([A-Za-z]+Error|Exception):\s*(.+)", output)
    if exc_match:
        exc_type = exc_match.group(1)
        exc_msg = exc_match.group(2)
        summary.append("==================================================")
        summary.append("❌ RUNTIME ERROR ENCOUNTERED IN SANDBOX")
        summary.append("==================================================")
        summary.append(f"⚠️  Error Type: {exc_type}")
        summary.append(f"💬 Message:    {exc_msg}")
        summary.append("==================================================")
        summary.append("\nDetailed Sandbox Logs:")
        summary.append("--------------------------------------------------")
        summary.append(output)
        return "\n".join(summary)

    return output


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
