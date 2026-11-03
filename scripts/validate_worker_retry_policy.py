#!/usr/bin/env python3
"""Validate the R03.52.4 Worker Retry Policy Registry contract."""
from __future__ import annotations
import json
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/worker-retry-policy.schema.v1alpha1.json").read_text())
POLICY = json.loads((ROOT / "contracts/worker-retry-policy.v1alpha1.json").read_text())

def main():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    errors = list(jsonschema.Draft202012Validator(
        SCHEMA, format_checker=jsonschema.FormatChecker()
    ).iter_errors(POLICY))
    if errors:
        raise SystemExit("Worker Retry Policy schema: " + errors[0].message)
    if not isinstance(POLICY.get("policy_version"), str) or not POLICY["policy_version"]:
        raise SystemExit("policy_version is required")
    codes = [item["error_code"] for item in POLICY["policies"]]
    if len(codes) != len(set(codes)):
        raise SystemExit("duplicate Worker Retry Policy error_code")
    if POLICY["default_policy"]["retryable"]:
        raise SystemExit("default policy must fail closed")
    if POLICY["default_policy"]["error_code"] in codes:
        raise SystemExit("default error_code collides with explicit policy")
    for item in POLICY["policies"]:
        if type(item["base_delay_micros"]) is not int or type(item["max_delay_micros"]) is not int:
            raise SystemExit("retry delays must be integer microseconds: " + item["error_code"])
        if item["max_delay_micros"] < item["base_delay_micros"]:
            raise SystemExit("max delay lower than base delay: " + item["error_code"])
    print(f"PASS: Worker Retry Policy Registry; {len(codes)} explicit error policies")
if __name__ == "__main__":
    main()
