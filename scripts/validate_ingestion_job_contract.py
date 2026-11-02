#!/usr/bin/env python3
"""Static validation for the R03.51 machine-readable Job contract."""
import json
from pathlib import Path
import jsonschema

schema = json.loads(Path("contracts/package-ingestion-job.schema.v1alpha1.json").read_text())
jsonschema.Draft202012Validator.check_schema(schema)
validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
base = {"schema_version":"1alpha1","tenant_id":"t1","job_id":"j1","session_id":"s1","package_id":"p1","package_version":"1.0.0","job_type":"validate","status":"queued","priority":0,"attempt_count":0,"maximum_attempts":5,"available_at":"2026-11-02T00:00:00Z","lease_owner":None,"lease_expires_at":None,"lease_epoch":0,"last_error_code":None,"last_error_safe_message":None,"completed_at":None,"created_at":"2026-11-02T00:00:00Z","updated_at":"2026-11-02T00:00:00Z"}
assert validator.is_valid(base), list(validator.iter_errors(base))
running = dict(base,status="running",lease_owner="worker-1",lease_expires_at="2026-11-02T00:01:00Z",attempt_count=1,lease_epoch=1)
assert validator.is_valid(running), list(validator.iter_errors(running))
succeeded = dict(base,status="succeeded",completed_at="2026-11-02T00:02:00Z")
assert validator.is_valid(succeeded), list(validator.iter_errors(succeeded))
bad = dict(running,status="unknown")
assert not validator.is_valid(bad), "unknown Job state must reject"
print("R03.51 Job Schema: queued/running/succeeded accepted; unknown state rejected")
