#!/usr/bin/env python3
"""Static policy guard for repository-wide GitHub Actions admission."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
GLOBAL_GROUP = "stem-lab-global-ci"
ALLOWED_ROOT_EVENTS = {"pull_request", "push", "workflow_dispatch"}


def fail(message: str) -> None:
    print(f"CI workflow policy violation: {message}", file=sys.stderr)
    raise SystemExit(1)


def top_level_block(content: str, name: str) -> list[str]:
    lines = content.splitlines()
    header = f"{name}:"
    try:
        start = next(i for i, line in enumerate(lines) if line == header)
    except StopIteration:
        return []
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith((" ", "\t", "#")):
            break
        block.append(line)
    return block


def event_names(content: str, path: Path) -> set[str]:
    block = top_level_block(content, "on")
    if not block:
        fail(f"{path.relative_to(ROOT)} has no explicit on: event mapping")
    return {
        match.group(1)
        for line in block
        if (match := re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)", line))
    }


def job_blocks(content: str) -> dict[str, str]:
    lines = top_level_block(content, "jobs")
    if not lines:
        fail("root workflow has no jobs mapping")
    headers = [
        (index, match.group(1))
        for index, line in enumerate(lines)
        if (match := re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line))
    ]
    blocks: dict[str, str] = {}
    for index, (start, name) in enumerate(headers):
        end = headers[index + 1][0] if index + 1 < len(headers) else len(lines)
        blocks[name] = "\n".join(lines[start + 1 : end])
    return blocks


def main() -> int:
    files = sorted(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml")))
    if not files:
        fail("no workflow files found")

    root_workflows: list[tuple[Path, str, set[str]]] = []
    for path in files:
        content = path.read_text(encoding="utf-8")
        events = event_names(content, path)
        if not events:
            fail(f"{path.relative_to(ROOT)} has an empty event mapping")
        if events == {"workflow_call"}:
            continue
        root_workflows.append((path, content, events))

    if len(root_workflows) != 1:
        fail(
            "exactly one event-triggered root workflow is allowed; "
            f"found {len(root_workflows)}"
        )

    path, content, events = root_workflows[0]
    relative = path.relative_to(ROOT)
    unexpected = events - ALLOWED_ROOT_EVENTS
    if unexpected:
        fail(f"{relative} has disallowed trigger events: {sorted(unexpected)}")

    concurrency = "\n".join(top_level_block(content, "concurrency"))
    if not concurrency:
        fail(f"{relative} is missing workflow-level concurrency")
    if not re.search(rf"(?m)^  group: {re.escape(GLOBAL_GROUP)}\s*$", concurrency):
        fail(f"{relative} must use concurrency group {GLOBAL_GROUP!r}")
    if not re.search(r"(?m)^  cancel-in-progress: false\s*$", concurrency):
        fail(f"{relative} must set cancel-in-progress: false")
    if not re.search(r"(?m)^  queue: single\s*$", concurrency):
        fail(f"{relative} must set queue: single")

    permissions = "\n".join(top_level_block(content, "permissions"))
    if not re.search(r"(?m)^  actions: read\s*$", permissions):
        fail(f"{relative} must grant actions: read for admission marker lookup")

    jobs = job_blocks(content)
    gate = jobs.get("ci-admission")
    if gate is None:
        fail(f"{relative} is missing the ci-admission job")
    if not re.search(
        r"(?m)^      admitted: \$\{\{ steps\.admission\.outputs\.admitted \}\}\s*$",
        gate,
    ):
        fail("ci-admission must export steps.admission.outputs.admitted")
    if "python scripts/ci_admission.py" not in gate:
        fail("ci-admission must run scripts/ci_admission.py")
    if "python scripts/test_ci_result.py" not in gate:
        fail("ci-admission must run scripts/test_ci_result.py")
    if not all(
        token in gate
        for token in (
            "- name: Persist repository-wide admission marker",
            "if: steps.admission.outputs.admitted == 'true'",
            "uses: actions/upload-artifact@v4",
        )
    ):
        fail("ci-admission must upload the marker artifact only after admission")

    for job_name, block in jobs.items():
        if job_name in {"ci-admission", "ci-result"}:
            continue
        if not re.search(r"(?m)^    needs: ci-admission\s*$", block):
            fail(f"job {job_name!r} must depend on ci-admission")
        if not re.search(
            r"(?m)^    if: needs\.ci-admission\.outputs\.admitted == 'true'\s*$",
            block,
        ):
            fail(f"job {job_name!r} must run only when admission is granted")

    result = jobs.get("ci-result")
    if result is None:
        fail("root workflow is missing the mandatory ci-result aggregation job")
    if not re.search(r"(?m)^    name: CI result\s*$", result):
        fail("ci-result must publish the stable required check name 'CI result'")
    if not re.search(r"(?m)^    if: always\(\)\s*$", result):
        fail("ci-result must run with if: always()")
    for dependency in ("ci-admission", "validate-contracts", "tenant-ed25519-verifier"):
        if not re.search(rf"(?m)^      - {re.escape(dependency)}\s*$", result):
            fail(f"ci-result must aggregate {dependency!r}")
    for job_name in jobs:
        if job_name in {"ci-admission", "ci-result"}:
            continue
        if not re.search(rf"(?m)^      - {re.escape(job_name)}\s*$", result):
            fail(f"ci-result must aggregate validation job {job_name!r}")
    if "python scripts/ci_result.py" not in result:
        fail("ci-result must run scripts/ci_result.py")

    print(
        f"CI workflow policy valid: one root workflow ({relative}), "
        f"global lock {GLOBAL_GROUP}, 600-second admission gate, truthful CI result."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
