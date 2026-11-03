#!/usr/bin/env python3
"""Fail-closed aggregation for the repository's required CI result check."""
from __future__ import annotations

import os
import sys
from typing import Mapping

REQUIRED_VALIDATION_JOBS = ("validate-contracts", "tenant-ed25519-verifier")


def final_ci_decision(
    admission_result: str,
    admitted: str,
    validation_results: Mapping[str, str],
) -> tuple[bool, str]:
    """Return whether the complete CI run passed and an operator-facing reason.

    A cooldown rejection is deliberately non-successful: it must block a merge
    until a later run performs the full validation suite. A skipped validation
    job is never interpreted as a successful validation.
    """
    if admission_result != "success":
        return False, f"CI BLOCKED: admission job concluded {admission_result!r}; validation was not authorized."

    if admitted == "false":
        return False, "CI DEFERRED: the repository-wide 600-second cooldown is active; rerun after it expires."
    if admitted != "true":
        return False, f"CI BLOCKED: admission output is missing or invalid ({admitted!r})."

    missing = [name for name in REQUIRED_VALIDATION_JOBS if name not in validation_results]
    if missing:
        return False, f"CI BLOCKED: missing validation job result(s): {', '.join(missing)}."

    non_success = [
        f"{name}={validation_results[name]}"
        for name in REQUIRED_VALIDATION_JOBS
        if validation_results[name] != "success"
    ]
    if non_success:
        return False, "CI FAILED: required validation job(s) did not succeed: " + ", ".join(non_success) + "."

    return True, "CI PASSED: admission was granted and every required validation job succeeded."


def main() -> int:
    admission_result = os.environ.get("CI_ADMISSION_RESULT", "")
    admitted = os.environ.get("CI_ADMITTED", "")
    validation_results = {
        "validate-contracts": os.environ.get("CI_VALIDATE_CONTRACTS_RESULT", ""),
        "tenant-ed25519-verifier": os.environ.get("CI_TENANT_ED25519_RESULT", ""),
    }
    passed, message = final_ci_decision(admission_result, admitted, validation_results)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## " + message.split(":", 1)[0] + "\n\n" + message + "\n")
    if passed:
        print(message)
        return 0
    print(f"::error::{message}", file=sys.stderr)
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
