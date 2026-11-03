#!/usr/bin/env python3
"""Read-only reconciliation of current PR/main heads against the required CI result."""
from __future__ import annotations
import argparse, json, os, re, sys
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
WORKFLOW_PATH = ".github/workflows/contract-validation.yml"
REQUIRED_CHECK = "CI result"
REQUIRED_APP_ID = 15368
ACTIVE_STATUSES = {"queued", "in_progress", "requested", "waiting", "pending"}
SUCCESS, ACTIVE, RECOVERY, UNKNOWN = "COVERED_SUCCESS", "ACTIVE", "RECOVERY_REQUIRED", "UNKNOWN"

class ReconcileError(RuntimeError):
    """GitHub API read failure or unusable response."""

@dataclass(frozen=True)
class Target:
    kind: str
    name: str
    number: int | None
    sha: str

@dataclass(frozen=True)
class Finding:
    kind: str
    name: str
    number: int | None
    sha: str
    state: str
    run_id: int | None
    reason: str

class GitHubReadOnly:
    def __init__(self, token: str | None, api_root: str = API_ROOT, timeout: int = 20):
        self.api_root, self.timeout, self.token = api_root.rstrip("/"), timeout, token

    def get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.api_root + path
        if query:
            url += "?" + urlencode(query)
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "stem-lab-ci-reconciliation-readonly"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            with urlopen(Request(url, headers=headers, method="GET"), timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise ReconcileError(f"GitHub API read failed for {path}: {type(exc).__name__}") from None
        if not isinstance(payload, (dict, list)):
            raise ReconcileError(f"GitHub API returned an unsupported response for {path}")
        return payload

    def list_all(self, path: str, key: str, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for page in range(1, 11):
            params = dict(query or {})
            params.update({"per_page": 100, "page": page})
            payload = self.get(path, params)
            if isinstance(payload, list) and key == "items":
                items = payload
            elif isinstance(payload, dict):
                items = payload.get(key)
            else:
                items = None
            if not isinstance(items, list):
                raise ReconcileError(f"GitHub API response omitted {key!r} for {path}")
            results.extend(item for item in items if isinstance(item, dict))
            if len(items) < 100:
                return results
        raise ReconcileError(f"Pagination safety limit reached for {path}")

def run_id_from_details_url(value: str) -> int | None:
    match = re.search(r"/actions/runs/([0-9]+)/job/[0-9]+(?:$|[?#])", value)
    return int(match.group(1)) if match else None

def classify_target(target: Target, workflow_runs: list[dict[str, Any]], check_runs: list[dict[str, Any]]) -> Finding:
    relevant = [r for r in workflow_runs if r.get("head_sha") == target.sha and r.get("path") == WORKFLOW_PATH]
    active_runs = [r for r in relevant if r.get("status") in ACTIVE_STATUSES]
    if active_runs:
        selected = max(active_runs, key=lambda r: int(r.get("run_attempt") or 1))
        return Finding(target.kind, target.name, target.number, target.sha, ACTIVE, selected.get("id"),
                       "matching required workflow run is queued or in progress")
    by_id = {r.get("id"): r for r in relevant if isinstance(r.get("id"), int)}
    successful_ids = {rid for rid, r in by_id.items()
                      if r.get("status") == "completed" and r.get("conclusion") == "success"}
    matching_checks = [
        c for c in check_runs
        if c.get("name") == REQUIRED_CHECK and isinstance(c.get("app"), dict)
        and c["app"].get("id") == REQUIRED_APP_ID and c.get("status") == "completed"
        and c.get("conclusion") == "success"
    ]
    for check in matching_checks:
        rid = run_id_from_details_url(str(check.get("details_url") or ""))
        if rid in successful_ids:
            return Finding(target.kind, target.name, target.number, target.sha, SUCCESS, rid,
                           "exact-SHA CI result succeeded under the required GitHub Actions integration")
    if relevant:
        latest = max(relevant, key=lambda r: (str(r.get("created_at") or ""), int(r.get("run_attempt") or 1)))
        reason = ("workflow run completed without a matching successful CI result check"
                  if latest.get("conclusion") == "success"
                  else f"latest matching workflow run is {latest.get('status')}/{latest.get('conclusion')}")
        return Finding(target.kind, target.name, target.number, target.sha, RECOVERY, latest.get("id"), reason)
    return Finding(target.kind, target.name, target.number, target.sha, RECOVERY, None,
                   "no run for the required workflow was found for this exact SHA")

def discover_targets(api: GitHubReadOnly, owner: str, repo: str, base: str) -> list[Target]:
    branch = api.get(f"/repos/{owner}/{repo}/branches/{base}")
    commit = branch.get("commit")
    sha = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ReconcileError(f"could not resolve the current {base!r} branch SHA")
    targets = [Target("main", base, None, sha)]
    pulls = api.list_all(f"/repos/{owner}/{repo}/pulls", "items",
                         {"state": "open", "base": base, "sort": "updated", "direction": "desc"})
    for pull in pulls:
        head = pull.get("head")
        head_sha = head.get("sha") if isinstance(head, dict) else None
        number, title = pull.get("number"), pull.get("title")
        if isinstance(head_sha, str) and re.fullmatch(r"[0-9a-f]{40}", head_sha) and isinstance(number, int):
            targets.append(Target("pull_request", str(title or f"PR #{number}"), number, head_sha))
    return targets

def reconcile(api: GitHubReadOnly, owner: str, repo: str, base: str) -> list[Finding]:
    findings = []
    for target in discover_targets(api, owner, repo, base):
        try:
            runs = api.list_all(f"/repos/{owner}/{repo}/actions/runs", "workflow_runs", {"head_sha": target.sha})
            checks = api.list_all(f"/repos/{owner}/{repo}/commits/{target.sha}/check-runs", "check_runs")
            findings.append(classify_target(target, runs, checks))
        except ReconcileError as exc:
            findings.append(Finding(target.kind, target.name, target.number, target.sha, UNKNOWN, None, str(exc)))
    return findings

def render_markdown(findings: list[Finding]) -> str:
    lines = ["| Target | SHA | State | Run | Reason |", "|---|---|---|---:|---|"]
    for f in findings:
        label = f"main:{f.name}" if f.kind == "main" else f"PR #{f.number}: {f.name}"
        lines.append(f"| {label} | {f.sha[:12]} | **{f.state}** | {f.run_id or '—'} | {f.reason.replace('|', chr(92) + '|')} |")
    counts = {s: sum(f.state == s for f in findings) for s in (SUCCESS, ACTIVE, RECOVERY, UNKNOWN)}
    lines += ["", "Summary: " + ", ".join(f"{k}={v}" for k, v in counts.items()), "",
              "Read-only report: no workflow was dispatched or rerun; no GitHub resource was modified."]
    return "\n".join(lines)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--base", default="main", help="base branch to reconcile (default: main)")
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
    print(json.dumps([asdict(f) for f in findings], indent=2) if args.json else render_markdown(findings))
    return 1 if any(f.state in {RECOVERY, UNKNOWN} for f in findings) else 0

if __name__ == "__main__":
    raise SystemExit(main())
