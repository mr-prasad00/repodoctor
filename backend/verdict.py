"""Deterministically map pipeline outcomes to RepoDoctor verdict statuses."""

from __future__ import annotations

from typing import Mapping, TypedDict


class SandboxOutcome(TypedDict):
    passed: bool
    output: str
    timed_out: bool


def decide_verdict(
    sandbox_result: Mapping[str, object] | None = None,
    *,
    invalid: bool = False,
    missing_fields: bool = False,
) -> str:
    """Return the exact verdict status for a validated pipeline outcome."""
    if invalid or missing_fields or sandbox_result is None:
        return "insufficient_info"
    if sandbox_result.get("timed_out") is True:
        return "insufficient_info"
    
    # Check exit code to distinguish assertion failure (exit code 1) from errors
    exit_code = sandbox_result.get("exit_code")
    if exit_code is not None:
        if exit_code == 0:
            return "not_reproducible"
        elif exit_code == 1:
            return "reproduced"
        else:
            return "insufficient_info"

    if sandbox_result.get("passed") is True:
        return "not_reproducible"
    return "reproduced"
