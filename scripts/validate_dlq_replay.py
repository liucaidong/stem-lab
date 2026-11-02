#!/usr/bin/env python3
"""Validate the R03.52.5 DLQ Replay Plan schema and example."""
from __future__ import annotations
import json
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/dlq-replay-plan.schema.v1alpha1.json").read_text())
FIXTURE = json.loads((ROOT / "contracts/examples/dlq-replay-plan.valid.json").read_text())

def main():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    errors = list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(FIXTURE))
    if errors:
        raise SystemExit("DLQ Replay Plan schema: " + errors[0].message)
    if FIXTURE["source_job_id"] == FIXTURE["new_job_id"]:
        raise SystemExit("DLQ replay must create a new Job ID")
    print("PASS: DLQ Replay Plan schema and new-Job identity invariant")
if __name__ == "__main__":
    main()
