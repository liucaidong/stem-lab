#!/usr/bin/env python3
"""Negative policy tests for CI workflow and dependency-lock invariants."""
from pathlib import Path

from validate_ci_workflow_policy import (
    enforce_apt_dependency_lock,
    enforce_artifact_retention,
    enforce_dependabot_config,
    enforce_job_permissions,
    enforce_node_dependency_lock,
    enforce_python_dependency_lock,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "contract-validation.yml"
DOCKERFILE = ROOT / "scripts" / "docker" / "pgsodium-postgres17.Dockerfile"


def rejected(label, callback):
    try:
        callback()
    except SystemExit:
        print(f"PASS: rejected {label}")
        return
    raise AssertionError(f"policy unexpectedly accepted {label}")


def main():
    content = WORKFLOW.read_text(encoding="utf-8")
    enforce_job_permissions(content, WORKFLOW)
    enforce_artifact_retention(content, WORKFLOW)
    enforce_python_dependency_lock(content, WORKFLOW)
    enforce_node_dependency_lock(content)
    enforce_apt_dependency_lock()
    enforce_dependabot_config()

    bad = content.replace("      actions: read", "      actions: write", 1)
    rejected("actions: write", lambda: enforce_job_permissions(bad, WORKFLOW))
    bad = content.replace("      contents: read\n", "", 1)
    rejected("missing contents: read", lambda: enforce_job_permissions(bad, WORKFLOW))
    bad = content.replace("          retention-days: 1\n", "", 1)
    rejected("unbounded marker retention", lambda: enforce_artifact_retention(bad, WORKFLOW))
    bad = content.replace("          retention-days: 7", "          retention-days: 30", 1)
    rejected("benchmark retention above seven days", lambda: enforce_artifact_retention(bad, WORKFLOW))
    bad = content.replace("--require-hashes", "", 1)
    rejected("Python install without hash enforcement", lambda: enforce_python_dependency_lock(bad, WORKFLOW))
    bad = content.replace("npm ci --ignore-scripts --no-audit --no-fund", "npm install pg", 1)
    rejected("mutable npm install", lambda: enforce_node_dependency_lock(bad))
    lock = (ROOT / "requirements-contract-validation.lock.txt").read_text(encoding="utf-8")
    bad_lock = lock.replace("--hash=sha256:", "--missing-hash:")
    rejected(
        "Python lock entry without SHA-256",
        lambda: enforce_python_dependency_lock(content, WORKFLOW, bad_lock),
    )
    benchmark = (ROOT / "scripts" / "benchmark_store_driver_pool.mjs").read_text(encoding="utf-8")
    bad_benchmark = benchmark.replace("createRequire", "createRequire_missing")
    rejected(
        "Node ESM dependency resolution regression",
        lambda: enforce_node_dependency_lock(content, bad_benchmark),
    )
    docker = DOCKERFILE.read_text(encoding="utf-8")
    bad_docker = docker.replace("PGDG_SERVER_DEV_SHA256=", "PGDG_SERVER_DEV_SHA256_MISSING=", 1)
    rejected(
        "PGDG package without checksum pin",
        lambda: enforce_apt_dependency_lock(bad_docker),
    )
    print("CI workflow and dependency-lock policy tests passed.")


if __name__ == "__main__":
    main()