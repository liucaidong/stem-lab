#!/usr/bin/env python3
"""Minimal CI admission output; GitHub Actions native concurrency owns scheduling."""
from __future__ import annotations

import os
import sys


def admission_decision() -> bool:
    """Admit the run; serialization and queue bounds are enforced by Actions."""
    return True


def write_step_output(admitted: bool) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise RuntimeError("GITHUB_OUTPUT is not set")
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"admitted={'true' if admitted else 'false'}\n")


def append_step_summary(message: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(message.rstrip() + "\n")


def main() -> int:
    try:
        admitted = admission_decision()
        write_step_output(admitted)
        append_step_summary(
            "## CI admission granted\n"
            "The run entered the GitHub Actions native concurrency queue.\n"
        )
        print("CI admission granted by the native GitHub Actions scheduling policy.")
        return 0
    except Exception as exc:
        print(f"::error::CI admission output failed closed: {exc}", file=sys.stderr)
        append_step_summary(
            "## CI admission error\n"
            "Admission output could not be written; required validation is blocked.\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
