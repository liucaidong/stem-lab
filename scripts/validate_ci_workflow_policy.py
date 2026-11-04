#!/usr/bin/env python3
"""Static policy guard for repository-wide GitHub Actions admission."""
from __future__ import annotations

import json
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



def enforce_job_permissions(content: str, path: Path) -> None:
    """Require least-privilege GITHUB_TOKEN permissions at job scope."""
    if not re.search(r"(?m)^permissions: \{\}\s*$", content):
        fail(f"{path.relative_to(ROOT)} must set workflow-level permissions: {{}}")
    jobs = job_blocks(content)
    expected = {
        "ci-admission": ("contents: read",),
        "validate-contracts": ("contents: read",),
        "tenant-ed25519-verifier": ("contents: read",),
        "ci-result": ("contents: read",),
    }
    if set(jobs) != set(expected):
        fail(f"workflow job set changed unexpectedly: {sorted(jobs)}")
    for job_name, scopes in expected.items():
        match = re.search(r"(?m)^    permissions:\n((?:      [a-z_]+: [a-z]+\n?)+)", jobs[job_name])
        if not match:
            fail(f"job {job_name!r} must declare explicit least-privilege permissions")
        actual = tuple(line.strip() for line in match.group(1).splitlines() if line.strip())
        if actual != scopes:
            fail(f"job {job_name!r} permissions must be exactly {scopes!r}; found {actual!r}")


def enforce_benchmark_artifact_retention(content: str, path: Path) -> None:
    """Require the benchmark artifact's bounded retention period."""
    benchmark = re.search(r"(?s)- name: Upload Store driver benchmark smoke results.*?with:\n(.*?)(?=\n      - name:|\Z)", content)
    if not benchmark or not re.search(r"(?m)^          retention-days: 7\s*$", benchmark.group(1)):
        fail("benchmark artifact must declare retention-days: 7")


def enforce_supply_chain_pins(content: str, path: Path) -> None:
    """Require immutable action refs and verified PostgreSQL/pgsodium inputs."""
    action_refs = re.findall(r"(?m)^\s*uses:\s*([^\s#]+)", content)
    if not action_refs:
        fail(f"{path.relative_to(ROOT)} has no action references to verify")
    for action_ref in action_refs:
        if action_ref.startswith("./"):
            continue
        if not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}",
            action_ref,
        ):
            fail(
                f"{path.relative_to(ROOT)} uses a non-immutable action reference: "
                f"{action_ref!r}; pin the verified full 40-character commit SHA"
            )

    postgres_ref = r"postgres:17\.11@sha256:[0-9a-f]{64}"
    if not re.search(rf"(?m)^\s*image:\s*{postgres_ref}\s*$", content):
        fail("PostgreSQL service image must use the approved version and SHA-256 digest")

    dockerfile = ROOT / "scripts" / "docker" / "pgsodium-postgres17.Dockerfile"
    if not dockerfile.is_file():
        fail("pgsodium PostgreSQL Dockerfile is missing")
    docker_content = dockerfile.read_text(encoding="utf-8")
    if not re.search(rf"(?m)^FROM\s+{postgres_ref}\s*$", docker_content):
        fail("pgsodium Dockerfile base image must use the approved PostgreSQL SHA-256 digest")
    if not re.search(r"(?m)^ARG PGSODIUM_SHA256=[0-9a-f]{64}$", docker_content):
        fail("pgsodium release asset must have an explicit SHA-256 lock")
    if "sha256sum -c -" not in docker_content:
        fail("pgsodium archive SHA-256 must be verified before extraction")



def enforce_python_dependency_lock(workflow_content: str, path: Path, lock_override: str | None = None) -> None:
    direct_path = ROOT / "requirements-contract-validation.txt"
    lock_path = ROOT / "requirements-contract-validation.lock.txt"
    if not direct_path.is_file() or not lock_path.is_file():
        fail("Python direct requirements and hash lock must both exist")
    direct = direct_path.read_text(encoding="utf-8")
    lock = lock_override if lock_override is not None else lock_path.read_text(encoding="utf-8")
    requirements = [
        line.strip() for line in direct.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    entries = [
        entry for entry in re.split(r"(?m)(?=^[A-Za-z0-9_.-]+==)", lock)
        if re.match(r"(?m)^[A-Za-z0-9_.-]+==", entry)
    ]
    if not entries:
        fail("Python dependency lock has no exact-version package entries")
    for entry in entries:
        if not re.search(r"(?m)^\s+--hash=sha256:[0-9a-f]{64}(?:\s+\\)?$", entry):
            fail("every Python locked package must carry at least one SHA-256 hash")
    for requirement in requirements:
        package = re.split(r"[\[<>=!~]", requirement, maxsplit=1)[0]
        normalized = package.lower().replace("_", "-")
        if not re.search(rf"(?im)^{re.escape(normalized)}==", lock):
            fail(f"direct Python dependency {package!r} is missing from the lock")
    if workflow_content.count(
        "python -m pip install --require-hashes -r requirements-contract-validation.lock.txt"
    ) != 2:
        fail("both Python CI jobs must install the unified lock with --require-hashes")
    if workflow_content.count("pip install") != 2:
        fail("untracked or inline pip install commands are not allowed in CI")


def enforce_node_dependency_lock(
    workflow_content: str,
    benchmark_override: str | None = None,
    package_override: str | None = None,
    lock_override: str | None = None,
) -> None:
    package_path = ROOT / "scripts" / "benchmarks" / "store-driver-node" / "package.json"
    lock_path = ROOT / "scripts" / "benchmarks" / "store-driver-node" / "package-lock.json"
    if not package_path.is_file() or not lock_path.is_file():
        fail("Node benchmark package.json and package-lock.json must both exist")
    package_text = package_override if package_override is not None else package_path.read_text(encoding="utf-8")
    lock_text = lock_override if lock_override is not None else lock_path.read_text(encoding="utf-8")
    package = json.loads(package_text)
    lock = json.loads(lock_text)
    approved_pg_version = "8.23.1"
    if package.get("dependencies", {}).get("pg") != approved_pg_version:
        fail(f"Node benchmark must pin pg exactly to {approved_pg_version}")
    if lock.get("lockfileVersion") != 3:
        fail("Node benchmark must use npm lockfileVersion 3")
    packages = lock.get("packages", {})
    if packages.get("node_modules/pg", {}).get("version") != approved_pg_version:
        fail(f"Node package lock does not lock pg@{approved_pg_version}")
    for package_name, metadata in packages.items():
        if package_name.startswith("node_modules/") and metadata.get("version") and not metadata.get("integrity"):
            fail(f"Node package {package_name!r} is missing an integrity digest")
    if "npm ci --ignore-scripts --no-audit --no-fund" not in workflow_content:
        fail("Node benchmark dependencies must be installed with npm ci and scripts disabled")
    if "npm install" in workflow_content:
        fail("mutable npm install commands are not allowed in CI")
    if "working-directory: scripts/benchmarks/store-driver-node" not in workflow_content:
        fail("npm ci must run in the isolated Node benchmark package directory")
    benchmark_script = ROOT / "scripts" / "benchmark_store_driver_pool.mjs"
    benchmark_content = benchmark_override if benchmark_override is not None else benchmark_script.read_text(encoding="utf-8")
    if not re.search(r"\bcreateRequire\b", benchmark_content) or "./benchmarks/store-driver-node/package.json" not in benchmark_content:
        fail("Node ESM benchmark must resolve pg from the isolated package directory")


def enforce_apt_dependency_lock(docker_override: str | None = None) -> None:
    dockerfile = ROOT / "scripts" / "docker" / "pgsodium-postgres17.Dockerfile"
    content = docker_override if docker_override is not None else dockerfile.read_text(encoding="utf-8")
    required = (
        "http://snapshot.debian.org/archive/debian/20261027T000000Z",
        "http://snapshot.debian.org/archive/debian-security/20261027T000000Z",
        'Acquire::Check-Valid-Until "false";',
        "build-essential=12.12",
        "ca-certificates=20250419+deb13u1",
        "clang-19=1:19.1.7-3+b1",
        "curl=8.14.1-2+deb13u7",
        "llvm-19-dev=1:19.1.7-3+b1",
        "pkg-config=1.8.1-4",
        "unzip=6.0-29+deb13u1",
        "PGDG_SERVER_DEV_VERSION=17.11-1.pgdg13+2",
        "PGDG_LIBPQ_DEV_VERSION=18.6-1.pgdg13+2",
    )
    for token in required:
        if token not in content:
            fail(f"APT dependency lock is missing required immutable input {token!r}")
    if "apt-get download" not in content or content.count("sha256sum -c -") < 3:
        fail("PGDG packages and source archives must be checksum-verified before use")
    for variable in ("PGDG_SERVER_DEV_SHA256", "PGDG_LIBPQ_DEV_SHA256"):
        if not re.search(rf"(?m)^ARG {variable}=[0-9a-f]{{64}}$", content):
            fail(f"{variable} must be an explicit SHA-256 digest")


def enforce_dependabot_config() -> None:
    """Require staggered weekly UTC windows and one open version PR per ecosystem."""
    path = ROOT / ".github" / "dependabot.yml"
    if not path.is_file():
        fail("Dependabot configuration is required")
    content = path.read_text(encoding="utf-8")
    expected = {
        "github-actions": "monday",
        "pip": "tuesday",
        "docker": "wednesday",
        "npm": "thursday",
    }
    blocks = re.findall(
        r'(?ms)^  - package-ecosystem: "([^"]+)"\n(.*?)(?=^  - package-ecosystem: |\Z)',
        content,
    )
    actual = {name: block for name, block in blocks}
    if set(actual) != set(expected):
        fail(f"Dependabot ecosystems must be exactly {sorted(expected)}; found {sorted(actual)}")
    for ecosystem, day in expected.items():
        block = actual[ecosystem]
        for token in (
            'interval: "weekly"',
            f'day: "{day}"',
            'time: "02:00"',
            'timezone: "Etc/UTC"',
            "open-pull-requests-limit: 1",
        ):
            if token not in block:
                fail(f"Dependabot {ecosystem!r} must contain {token!r}")
        if 'update-types: ["minor", "patch"]' not in block:
            fail(f"Dependabot {ecosystem!r} must retain minor/patch grouping")


def enforce_concurrency_contract(content: str, path: Path) -> None:
    """Enforce the global bounded queue and prevent pending-run replacement."""
    concurrency = "\n".join(top_level_block(content, "concurrency"))
    if not concurrency:
        fail(f"{path.relative_to(ROOT)} is missing workflow-level concurrency")
    if not re.search(rf"(?m)^  group: {re.escape(GLOBAL_GROUP)}\s*$", concurrency):
        fail(f"{path.relative_to(ROOT)} must use concurrency group {GLOBAL_GROUP!r}")
    if not re.search(r"(?m)^  cancel-in-progress: false\s*$", concurrency):
        fail(f"{path.relative_to(ROOT)} must set cancel-in-progress: false")
    if not re.search(r"(?m)^  queue: max\s*$", concurrency):
        fail(f"{path.relative_to(ROOT)} must set queue: max")
    for token in ("stem-lab-ci-admission", ".ci-admission/marker.json", "300-second"):
        if token in content:
            fail(f"{path.relative_to(ROOT)} still contains removed admission token {token!r}")


def enforce_native_admission(workflow_content: str, admission_source: str) -> None:
    """Reject any remaining artifact-marker or timed admission implementation."""
    for token in ("COOLDOWN_SECONDS", "MARKER_ARTIFACT_NAME", "MARKER_PATH"):
        if token in admission_source:
            fail(f"removed admission implementation remains: {token}")
    for token in ("stem-lab-ci-admission", ".ci-admission/marker.json", "300-second"):
        if token in workflow_content:
            fail(f"removed admission implementation remains: {token}")


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
    enforce_supply_chain_pins(content, path)
    enforce_job_permissions(content, path)
    enforce_benchmark_artifact_retention(content, path)
    enforce_python_dependency_lock(content, path)
    enforce_node_dependency_lock(content)
    enforce_apt_dependency_lock()
    enforce_dependabot_config()
    relative = path.relative_to(ROOT)
    unexpected = events - ALLOWED_ROOT_EVENTS
    if unexpected:
        fail(f"{relative} has disallowed trigger events: {sorted(unexpected)}")

    enforce_concurrency_contract(content, path)

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
        fail("ci-admission must execute the native admission output helper")
    if "python scripts/test_ci_result.py" not in gate:
        fail("ci-admission must run scripts/test_ci_result.py")
    if "python scripts/test_ci_reconcile.py" not in gate:
        fail("ci-admission must run scripts/test_ci_reconcile.py")
    if "stem-lab-ci-admission" in content or ".ci-admission/marker.json" in content:
        fail("artifact-based admission markers are forbidden")

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

    admission_source = (ROOT / "scripts" / "ci_admission.py").read_text(encoding="utf-8")
    enforce_native_admission(content, admission_source)

    print(
        f"CI workflow policy valid: one root workflow ({relative}), "
        f"native queue {GLOBAL_GROUP}/max, truthful CI result."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())