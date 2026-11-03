#!/usr/bin/env python3
"""Negative policy tests for CI workflow permissions and artifact retention."""
from pathlib import Path
from validate_ci_workflow_policy import enforce_artifact_retention, enforce_job_permissions

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "contract-validation.yml"

def rejected(label, fn):
    try:
        fn()
    except SystemExit:
        print(f"PASS: rejected {label}")
        return
    raise AssertionError(f"policy unexpectedly accepted {label}")

def main():
    content = WORKFLOW.read_text(encoding="utf-8")
    enforce_job_permissions(content, WORKFLOW)
    enforce_artifact_retention(content, WORKFLOW)
    bad = content.replace("      actions: read", "      actions: write", 1)
    rejected("actions: write", lambda: enforce_job_permissions(bad, WORKFLOW))
    bad = content.replace("      contents: read\n", "", 1)
    rejected("missing contents: read", lambda: enforce_job_permissions(bad, WORKFLOW))
    bad = content.replace("          retention-days: 1\n", "", 1)
    rejected("unbounded marker retention", lambda: enforce_artifact_retention(bad, WORKFLOW))
    bad = content.replace("          retention-days: 7", "          retention-days: 30", 1)
    rejected("benchmark retention above seven days", lambda: enforce_artifact_retention(bad, WORKFLOW))
    print("CI workflow permission and artifact-retention policy tests passed.")

if __name__ == "__main__":
    main()
