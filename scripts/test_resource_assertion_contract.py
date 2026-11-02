#!/usr/bin/env python3
"""Schema and semantic tests for the experimental Job-rooted assertion contract.

This validates a proposal/reference contract only. It does not verify signatures,
database relationships, RLS, nonce consumption, or production authorization.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
ASSERTION_PATH = ROOT / "contracts/worker-resource-assertion.schema.v2alpha1.json"
LEASE_PATH = ROOT / "contracts/worker-job-lease.schema.v2alpha1.json"
FIXTURE_PATH = ROOT / "contracts/examples/worker-resource-assertion.v2alpha1.valid.json"

ACTIONS = {
    "worker.job.renew",
    "worker.job.complete",
    "worker.job.fail",
    "worker.job.retry",
    "worker.job.dead_letter",
    "worker.dlq.replay",
    "worker.outbox.dispatch",
    "worker.receipt.reconcile",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_claims() -> dict:
    return load(FIXTURE_PATH)


def semantic_errors(claims: dict, *, max_lifetime: int = 120) -> list[str]:
    errors: list[str] = []
    if claims.get("action") not in ACTIONS:
        errors.append("unsupported action")
    iat, exp = claims.get("iat"), claims.get("exp")
    if isinstance(iat, bool) or not isinstance(iat, int):
        errors.append("iat must be an integer")
    if isinstance(exp, bool) or not isinstance(exp, int):
        errors.append("exp must be an integer")
    if isinstance(iat, int) and isinstance(exp, int):
        if exp <= iat:
            errors.append("exp must be greater than iat")
        if exp - iat > max_lifetime:
            errors.append("assertion lifetime exceeds configured maximum")
    if claims.get("v") != 2:
        errors.append("unsupported assertion version")
    action = claims.get("action")
    resource_type, resource_id = claims.get("resource_type"), claims.get("resource_id")
    if action in {
        "worker.job.renew", "worker.job.complete", "worker.job.fail",
        "worker.job.retry", "worker.job.dead_letter",
    } and (resource_type, resource_id) != ("job", claims.get("job_id")):
        errors.append("Job action must be rooted at the exact Job")
    elif action == "worker.dlq.replay" and resource_type != "dlq_item":
        errors.append("DLQ replay must be rooted at a DLQ item")
    elif action == "worker.outbox.dispatch" and resource_type != "outbox_event":
        errors.append("Outbox dispatch must be rooted at an Outbox event")
    elif action == "worker.receipt.reconcile" and resource_type != "receipt":
        errors.append("Receipt reconciliation must be rooted at a Receipt")
    return errors


def main() -> None:
    assertion_schema, lease_schema = load(ASSERTION_PATH), load(LEASE_PATH)
    jsonschema.Draft202012Validator.check_schema(assertion_schema)
    jsonschema.Draft202012Validator.check_schema(lease_schema)
    assertion_validator = jsonschema.Draft202012Validator(assertion_schema)
    lease_validator = jsonschema.Draft202012Validator(
        lease_schema, format_checker=jsonschema.FormatChecker()
    )

    claims = valid_claims()
    assert not list(assertion_validator.iter_errors(claims))
    assert not semantic_errors(claims)

    invalid_cases = []
    for field, value in [
        ("tenant_id", ""), ("job_id", ""), ("resource_type", "tenant"),
        ("resource_id", ""), ("session_id", ""), ("owner", ""),
        ("epoch", 0), ("operation_id", ""), ("aud", ""),
        ("action", "worker.job.delete"), ("nonce", "short"),
    ]:
        case = copy.deepcopy(claims)
        case[field] = value
        invalid_cases.append(case)
    for case in invalid_cases:
        assert list(assertion_validator.iter_errors(case)), "schema must reject malformed claim"

    assert "Job action must be rooted at the exact Job" in semantic_errors(
        {**claims, "resource_id": "job-2"}
    )
    assert "Job action must be rooted at the exact Job" in semantic_errors(
        {**claims, "job_id": "job-2"}
    )
    assert "DLQ replay must be rooted at a DLQ item" in semantic_errors({
        **claims, "action": "worker.dlq.replay", "resource_type": "job",
    })
    assert "Outbox dispatch must be rooted at an Outbox event" in semantic_errors({
        **claims, "action": "worker.outbox.dispatch",
    })

    unknown_claim = copy.deepcopy(claims)
    unknown_claim["tenant_role"] = "admin"
    assert list(assertion_validator.iter_errors(unknown_claim))

    assert semantic_errors({**claims, "exp": claims["iat"]}) == [
        "exp must be greater than iat"
    ]
    assert "assertion lifetime exceeds configured maximum" in semantic_errors(
        {**claims, "exp": claims["iat"] + 121}
    )

    lease = {
        "tenant_id": "tenant-a", "job_id": "job-1", "session_id": "session-1",
        "owner": "worker-1", "epoch": 7,
        "expires_at": datetime.now(timezone.utc).isoformat(),
    }
    assert not list(lease_validator.iter_errors(lease))
    for field in ("tenant_id", "job_id", "session_id", "owner", "epoch", "expires_at"):
        case = copy.deepcopy(lease)
        case.pop(field)
        assert list(lease_validator.iter_errors(case)), f"lease missing {field} must fail"

    print("PASS: v2alpha1 closed assertion claims, Job/Session/Owner/Epoch/Operation binding, "
          "action allowlist, time semantics, nonce shape, and versioned JobLease schema")


if __name__ == "__main__":
    main()
