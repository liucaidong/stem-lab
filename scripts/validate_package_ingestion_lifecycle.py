#!/usr/bin/env python3
"""Static Package ingestion lifecycle and idempotency contract validator."""
from __future__ import annotations
import copy, json
from datetime import datetime
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts/package-ingestion-session.schema.v1alpha1.json"
FIXTURE = ROOT / "contracts/examples/package-ingestion-lifecycle.fixtures.v1alpha1.json"

ALLOWED = {
    None: {"created"},
    "created": {"receiving", "rejected", "expired"},
    "receiving": {"received", "rejected", "expired"},
    "received": {"quarantined", "rejected", "expired"},
    "quarantined": {"validating", "rejected", "expired"},
    "validating": {"validated", "rejected", "quarantined"},
    "validated": {"revoked"},
    "rejected": set(),
    "revoked": set(),
    "expired": set(),
}

class LifecycleError(Exception):
    def __init__(self, code, message=""):
        self.code = code
        super().__init__(message or code)

def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON property: " + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)

def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def validate_lifecycle(session):
    schema = load(SCHEMA)
    errors = list(jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    ).iter_errors(session))
    if errors:
        raise LifecycleError("SCHEMA_INVALID", errors[0].message)
    if parse_time(session["expires_at"]) <= parse_time(session["created_at"]):
        raise LifecycleError("INVALID_SESSION_TTL")

    current, revision, sequence = None, 0, 0
    command_ids, idempotency_keys = set(), set()
    for transition in session["transitions"]:
        sequence += 1
        if transition["sequence"] != sequence:
            raise LifecycleError("TRANSITION_SEQUENCE_GAP")
        if transition["from_state"] != current:
            raise LifecycleError("BROKEN_STATE_CHAIN")
        if transition["expected_revision"] != revision:
            raise LifecycleError("REVISION_CONFLICT")
        if transition["resulting_revision"] != revision + 1:
            raise LifecycleError("REVISION_NOT_INCREMENTED")
        if transition["to_state"] not in ALLOWED[current]:
            raise LifecycleError("ILLEGAL_STATE_TRANSITION")
        if transition["command_id"] in command_ids:
            raise LifecycleError("DUPLICATE_COMMAND_ID")
        if transition["idempotency_key"] in idempotency_keys:
            raise LifecycleError("DUPLICATE_IDEMPOTENCY_TRANSITION")
        command_ids.add(transition["command_id"])
        idempotency_keys.add(transition["idempotency_key"])
        current = transition["to_state"]
        revision = transition["resulting_revision"]

    if current != session["status"]:
        raise LifecycleError("SESSION_STATUS_MISMATCH")
    if revision != session["revision"]:
        raise LifecycleError("SESSION_REVISION_MISMATCH")
    if parse_time(session["updated_at"]) < parse_time(session["transitions"][-1]["occurred_at"]):
        raise LifecycleError("UPDATED_AT_BEFORE_LAST_TRANSITION")

    if session["status"] == "validated":
        evidence = session["validation_evidence"]
        if evidence["verified_resource_count"] != evidence["resource_count"]:
            raise LifecycleError("RESOURCE_VERIFICATION_INCOMPLETE")
    if session["status"] in {"rejected", "revoked", "expired"}:
        if not session.get("terminal_reason_code") or not session["transitions"][-1].get("reason_code"):
            raise LifecycleError("TERMINAL_REASON_REQUIRED")
    return True

def idempotency_outcome(existing_digest, incoming_digest):
    if existing_digest == incoming_digest:
        return "REPLAY_EXISTING_RECEIPT"
    return "IDEMPOTENCY_KEY_CONFLICT"

def main():
    fixture = load(FIXTURE)
    session = fixture["valid_session"]
    validate_lifecycle(session)
    for item in fixture["idempotency_cases"]:
        actual = idempotency_outcome(item["existing_digest"], item["incoming_digest"])
        if actual != item["expected"]:
            raise SystemExit("idempotency outcome mismatch")

    mutations = {
        "illegal-transition": lambda s: s["transitions"][1].update(to_state="validated"),
        "broken-state-chain": lambda s: s["transitions"][2].update(from_state="created"),
        "revision-gap": lambda s: s["transitions"][2].update(expected_revision=9),
        "duplicate-command-id": lambda s: s["transitions"][1].update(command_id=s["transitions"][0]["command_id"]),
        "duplicate-idempotency-key": lambda s: s["transitions"][1].update(idempotency_key=s["transitions"][0]["idempotency_key"]),
        "missing-validation-evidence": lambda s: s["validation_evidence"].pop("archive_digest"),
        "unverified-resource-count": lambda s: s["validation_evidence"].update(verified_resource_count=6),
        "validated-to-receiving": lambda s: (s["transitions"][-1].update(to_state="receiving"), s.update(status="receiving")),
        "terminal-state-transition": lambda s: (
            s["transitions"].append({
                **copy.deepcopy(s["transitions"][-1]),
                "sequence":7,"from_state":"validated","to_state":"receiving",
                "command_id":"cmd-7","idempotency_key":"idem-7",
                "expected_revision":6,"resulting_revision":7,"occurred_at":"2026-11-02T10:00:07Z"
            }), s.update(status="receiving",revision=7)
        ),
        "missing-terminal-reason": lambda s: (
            s["transitions"][-1].update(to_state="rejected"),
            s["transitions"][-1].pop("reason_code",None),
            s.update(status="rejected",terminal_reason_code=None)
        )
    }
    for case in fixture["invalid_cases"]:
        candidate = copy.deepcopy(session)
        mutations[case](candidate)
        try:
            validate_lifecycle(candidate)
        except LifecycleError:
            pass
        else:
            raise SystemExit("invalid lifecycle accepted: " + case)

    print("PASS: Package ingestion lifecycle schema/state graph/revision chain/append-only sequence/validation evidence/terminal states; idempotency replay and conflict; 10 rejection cases")
    print("CONTRACT ONLY: no database persistence, upload API, worker lease, broker or production quarantine service")

if __name__ == "__main__":
    main()
