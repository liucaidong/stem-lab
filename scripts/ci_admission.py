#!/usr/bin/env python3
"""Repository-wide 300-second GitHub Actions admission gate.

The workflow-level concurrency group serializes gate evaluations. A successful
admission uploads a repository-visible Actions artifact. Later runs inspect the
latest marker artifact, which is shared across pull-request branch cache scopes.
Any API or state error fails closed so validation jobs cannot start accidentally.
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COOLDOWN_SECONDS = 300
MARKER_ARTIFACT_NAME = "stem-lab-ci-admission"
MARKER_PATH = Path(".ci-admission/marker.json")


def parse_timestamp(value: str) -> datetime:
    """Parse a GitHub RFC3339 timestamp and normalize it to UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def admission_decision(
    event_created_at: datetime,
    latest_marker_created_at: datetime | None,
    cooldown_seconds: int = COOLDOWN_SECONDS,
) -> tuple[bool, int]:
    """Return (admitted, remaining_seconds); boundary is inclusive at 300s."""
    if cooldown_seconds <= 0:
        raise ValueError("cooldown_seconds must be positive")
    if latest_marker_created_at is None:
        return True, 0
    elapsed = (event_created_at - latest_marker_created_at).total_seconds()
    if elapsed >= cooldown_seconds:
        return True, 0
    return False, max(1, math.ceil(cooldown_seconds - elapsed))


def github_get(path: str) -> dict[str, Any]:
    token = os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    if not token or not repo:
        raise RuntimeError("GH_TOKEN and GITHUB_REPOSITORY are required")
    url = f"{api_url}/repos/{repo}/{path.lstrip('/')}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "stem-lab-ci-admission",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"GitHub API request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub API returned a non-object response")
    return payload


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
        run_id = os.environ.get("GITHUB_RUN_ID")
        if not run_id:
            raise RuntimeError("GITHUB_RUN_ID is not set")

        current_run = github_get(f"actions/runs/{urllib.parse.quote(run_id)}")
        event_created_at = parse_timestamp(current_run["created_at"])

        query = urllib.parse.urlencode({"name": MARKER_ARTIFACT_NAME, "per_page": 1})
        artifact_response = github_get(f"actions/artifacts?{query}")
        artifacts = artifact_response.get("artifacts")
        if not isinstance(artifacts, list):
            raise RuntimeError("GitHub artifact response is missing its artifacts list")

        latest_marker_created_at: datetime | None = None
        if artifacts:
            latest_marker_created_at = max(
                parse_timestamp(item["created_at"])
                for item in artifacts
                if isinstance(item, dict) and item.get("created_at")
            )

        admitted, remaining = admission_decision(
            event_created_at,
            latest_marker_created_at,
        )

        if not admitted:
            write_step_output(False)
            append_step_summary(
                "## CI admission rejected\n"
                f"A repository-wide CI admission was recorded less than {COOLDOWN_SECONDS} seconds "
                "before this event. Heavy validation jobs were not started.\n"
                f"Remaining cooldown: **{remaining} seconds**.\n"
            )
            print(
                f"CI admission rejected: repository cooldown active; "
                f"{remaining}s remaining. No validation jobs will run."
            )
            return 0

        MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        MARKER_PATH.write_text(
            json.dumps(
                {
                    "repository": os.environ["GITHUB_REPOSITORY"],
                    "run_id": run_id,
                    "event_created_at": event_created_at.isoformat(),
                    "cooldown_seconds": COOLDOWN_SECONDS,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_step_output(True)
        append_step_summary(
            "## CI admission granted\n"
            f"Repository-wide **{COOLDOWN_SECONDS}-second** cooldown acquired. "
            "The admission marker will be persisted before validation jobs start.\n"
        )
        print(
            f"CI admission granted for run {run_id}; "
            f"next repository-wide admission is blocked for {COOLDOWN_SECONDS}s."
        )
        return 0
    except Exception as exc:
        print(f"::error::CI admission gate failed closed: {exc}", file=sys.stderr)
        append_step_summary(
            "## CI admission gate error\n"
            "The gate could not verify repository-wide cooldown state. "
            "Validation jobs were blocked (fail-closed).\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
