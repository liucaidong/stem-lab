#!/usr/bin/env python3
"""Read-only reconciliation of every open PR head and the current base branch."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
WORKFLOW_PATH = ".github/workflows/contract-validation.yml"
REQUIRED_CHECK = "CI result"
REQUIRED_APP_ID = 15368
ACTIVE_STATUSES = {"queued", "in_progress", "requested", "waiting", "pending"}
SUCCESS, ACTIVE, RECOVERY, UNKNOWN = (
    "COVERED_SUCCESS", "ACTIVE", "RECOVERY_REQUIRED", "UNKNOWN"
)
SHA_RE = re.compile(r"[0-9a-f]{40}")


class ReconcileError(RuntimeError):
    """GitHub API read failure or unusable response."""


@dataclass(frozen=True)
class Target:
    kind: str
    name: str
    number: int | None
    sha: str
    base_ref: str | None = None
    base_sha: str | None = None


@dataclass(frozen=True)
class Finding:
    kind: str
    name: str
    number: int | None
    sha: str
    state: str
    run_id: int | None
    reason: str
    base_ref: str | None = None
    base_sha: str | None = None


class GitHubReadOnly:
    def __init__(self, token: str | None, api_root: str = API_ROOT, timeout: int = 20):
        self.api_root, self.timeout, self.token = api_root.rstrip("/"), timeout, token

    def get(
        self, path: str, query: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        url = self.api_root + path
        if query:
            url += "?" + urlencode(query)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "stem-lab-ci-reconciliation-readonly",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            with urlopen(Request(url, headers=headers, method="GET"), timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise ReconcileError(
                f"GitHub API read failed for {path}: {type(exc).__name__}"
            ) from None
        if isinstance(payload, list):
            if not all(isinstance(item, dict) for item in payload):
                raise ReconcileError(f"GitHub API returned malformed list entries for {path}")
            return payload
        if isinstance(payload, dict):
            return payload
        raise ReconcileError(f"GitHub API returned an unsupported response for {path}")

    def list_all(
        self, path: str, key: str, query: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        # Permit a page-11 empty response when exactly 1,000 entries exist.
        # If page 100 is still full, stop rather than silently truncate.
        for page in range(1, 101):
            params = dict(query or {})
            params.update({"per_page": 100, "page": page})
            payload = self.get(path, params)
            if isinstance(payload, list) and key == "items":
                items = payload
            elif isinstance(payload, dict):
                items = payload.get(key)
            else:
                items = None
            if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                raise ReconcileError(f"GitHub API response omitted or malformed {key!r} for {path}")
            results.extend(items)
            if len(items) < 100:
                return results
        raise ReconcileError(f"Pagination safety limit reached for {path}")


def parse_aware_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp only when its timezone is explicit."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def run_id_from_details_url(value: str) -> int | None:
    match = re.fullmatch(
        r"https://github\.com/[^/]+/[^/]+/actions/runs/([0-9]+)/job/[0-9]+/?",
        value,
    )
    return int(match.group(1)) if match else None


def check_started_in_latest_attempt(
    check: dict[str, Any], latest_run: dict[str, Any]
) -> bool:
    # A workflow rerun reuses its run ID; the start-time boundary distinguishes attempts.
    run_started = parse_aware_timestamp(latest_run.get("run_started_at"))
    check_started = parse_aware_timestamp(check.get("started_at"))
    return run_started is not None and check_started is not None and check_started >= run_started


def finding(target: Target, state: str, run_id: int | None, reason: str) -> Finding:
    return Finding(
        target.kind, target.name, target.number, target.sha, state, run_id, reason,
        target.base_ref, target.base_sha,
    )


def classify_target(
    target: Target,
    workflow_runs: list[dict[str, Any]],
    check_runs: list[dict[str, Any]],
) -> Finding:
    relevant = [
        run for run in workflow_runs
        if run.get("head_sha") == target.sha and run.get("path") == WORKFLOW_PATH
    ]
    if not relevant:
        return finding(
            target, RECOVERY, None,
            "no run for the required workflow was found for this exact SHA",
        )

    parsed_created = [parse_aware_timestamp(run.get("created_at")) for run in relevant]
    if any(timestamp is None for timestamp in parsed_created):
        return finding(
            target, RECOVERY, None,
            "one or more matching workflow runs have missing or invalid created_at timestamps",
        )
    for run in relevant:
        if not isinstance(run.get("id"), int) or not isinstance(run.get("run_attempt", 1), int):
            return finding(target, RECOVERY, None, "matching workflow run has invalid id or run_attempt")

    latest = max(
        relevant,
        key=lambda run: (
            parse_aware_timestamp(run["created_at"]),
            run.get("run_attempt", 1),
            run["id"],
        ),
    )
    run_id = latest["id"]

    if latest.get("status") in ACTIVE_STATUSES:
        return finding(
            target, ACTIVE, run_id,
            "latest matching required workflow run is queued or in progress",
        )

    if latest.get("status") == "completed" and latest.get("conclusion") == "success":
        for check in check_runs:
            if (
                check.get("name") == REQUIRED_CHECK
                and isinstance(check.get("app"), dict)
                and check["app"].get("id") == REQUIRED_APP_ID
                and check.get("status") == "completed"
                and check.get("conclusion") == "success"
                and check.get("head_sha") == target.sha
                and check_started_in_latest_attempt(check, latest)
                and run_id_from_details_url(str(check.get("details_url") or "")) == run_id
            ):
                return finding(
                    target, SUCCESS, run_id,
                    "latest exact-SHA workflow run and its same-run required CI result both succeeded",
                )

        return finding(
            target, RECOVERY, run_id,
            "latest workflow run succeeded but has no matching successful exact-SHA CI result check",
        )

    return finding(
        target, RECOVERY, run_id,
        f"latest matching workflow run is {latest.get('status')}/{latest.get('conclusion')}",
    )


def discover_targets(
    api: GitHubReadOnly, owner: str, repo: str, base: str
) -> list[Target]:
    branch = api.get(f"/repos/{owner}/{repo}/branches/{base}")
    if not isinstance(branch, dict):
        raise ReconcileError(f"could not read the {base!r} branch object")
    commit = branch.get("commit")
    main_sha = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(main_sha, str) or not SHA_RE.fullmatch(main_sha):
        raise ReconcileError(f"could not resolve the current {base!r} branch SHA")

    targets = [Target("main", base, None, main_sha, base, main_sha)]
    # Deliberately do not filter by base: the audit covers every open PR head.
    pulls = api.list_all(
        f"/repos/{owner}/{repo}/pulls", "items",
        {"state": "open", "sort": "updated", "direction": "desc"},
    )
    for pull in pulls:
        head = pull.get("head")
        base_obj = pull.get("base")
        head_sha = head.get("sha") if isinstance(head, dict) else None
        number = pull.get("number")
        base_ref = base_obj.get("ref") if isinstance(base_obj, dict) else None
        base_sha = base_obj.get("sha") if isinstance(base_obj, dict) else None
        if (
            not isinstance(number, int)
            or not isinstance(head_sha, str) or not SHA_RE.fullmatch(head_sha)
            or not isinstance(base_ref, str) or not base_ref
            or not isinstance(base_sha, str) or not SHA_RE.fullmatch(base_sha)
        ):
            raise ReconcileError("an open pull request has incomplete or malformed head/base metadata")
        targets.append(
            Target(
                "pull_request", str(pull.get("title") or f"PR #{number}"),
                number, head_sha, base_ref, base_sha,
            )
        )
    return targets


def reconcile(api: GitHubReadOnly, owner: str, repo: str, base: str) -> list[Finding]:
    findings: list[Finding] = []
    for target in discover_targets(api, owner, repo, base):
        try:
            runs = api.list_all(
                f"/repos/{owner}/{repo}/actions/runs", "workflow_runs",
                {"head_sha": target.sha},
            )
            checks = api.list_all(
                f"/repos/{owner}/{repo}/commits/{target.sha}/check-runs", "check_runs"
            )
            findings.append(classify_target(target, runs, checks))
        except ReconcileError as exc:
            findings.append(finding(target, UNKNOWN, None, str(exc)))
    return findings


def cell(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", r"\|").replace("\n", " ")


def render_markdown(findings: list[Finding]) -> str:
    lines = [
        "| Target | Head SHA | Base branch | Base SHA | State | Run | Reason |",
        "|---|---|---|---|---|---:|---|",
    ]
    for item in findings:
        label = f"main:{item.name}" if item.kind == "main" else f"PR #{item.number}: {item.name}"
        lines.append(
            f"| {cell(label)} | {item.sha} | {cell(item.base_ref)} | "
            f"{cell(item.base_sha)} | **{item.state}** | {item.run_id or '—'} | {cell(item.reason)} |"
        )
    counts = {
        state: sum(item.state == state for item in findings)
        for state in (SUCCESS, ACTIVE, RECOVERY, UNKNOWN)
    }
    lines += [
        "",
        "Summary: " + ", ".join(f"{key}={value}" for key, value in counts.items()),
        "",
        "Read-only report: no workflow was dispatched or rerun; no GitHub resource was modified.",
        "Ruleset applicability: repository Ruleset checks apply to PRs targeting the protected base branch only; other base branches are reported for CI coverage but are not claimed to be governed by that Ruleset.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--base", default="main", help="protected base branch to include (default: main)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("--repo must be owner/repository")
    owner, repo = args.repo.split("/", 1)
    api = GitHubReadOnly(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    try:
        findings = reconcile(api, owner, repo, args.base)
    except ReconcileError as exc:
        print(f"CI reconciliation unavailable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps([asdict(item) for item in findings], indent=2) if args.json else render_markdown(findings))
    return 1 if any(item.state in {RECOVERY, UNKNOWN} for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
