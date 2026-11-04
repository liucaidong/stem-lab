# R03.52.7.3.11.5 — Protocol and Security Hardening Delta

**Status:** reference-level remediation batch; production implementation entry remains blocked pending integrated UOW, deployment and security proof.

## Changes in this batch

1. Request Digest SQL asset is constrained to six complete function definitions; the PostgreSQL conformance test executes the entire shipped SQL file rather than extracting fragments.
2. Request JSON and canonical digest inputs have a 64 KiB budget in Python and PostgreSQL. Assertion `epoch`, `iat` and `exp` are bounded by the JSON-safe integer ceiling.
3. Receipt arbitration binds digest, operation ID, resource type and resource ID. A separate `STABLE` SELECT-only lookup handles missing/pending/terminal reads without reserving a Receipt. Finalization binds tenant, action, idempotency key and digest; outcome JSON is object-only and capped at 16 KiB.
4. Receipt helper table/functions revoke PUBLIC privileges. Explicit grants for a dedicated runtime role still require a reviewed deployment migration; this is not a production RLS or signed-tenant-context implementation.
5. Retry decisions are registry-owned, policy-versioned and expressed in integer microseconds. The classifier returns only an error code. Claimed Jobs carry persisted `maximum_attempts`; failure Store commands carry `retry_policy_version`.
6. DLQ Replay is excluded from the v2alpha2 digest/assertion action allowlist until trusted actor provenance and atomic source-row/new-Job/audit UOW are implemented.

## Added/updated acceptance evidence

- Full-file PostgreSQL digest SQL execution and oversized-envelope rejection.
- Python raw JSON and canonical request size tests.
- Receipt exact-retry fixture, identity mismatch, read-only missing lookup, finalization binding, PUBLIC ACL catalog check and concurrent arbitration.
- Retry registry version, integer-unit, attempt-limit and Worker Runtime delegation tests.
- Store Protocol schema/value tests for `maximum_attempts`, `retry_delay_micros` and `retry_policy_version`.

## Still-blocking production gates

- Full 81-path semantic source audit and cross-reference scan.
- Durable v2alpha2 Nonce Ledger and signed-assertion-to-tenant-context binding.
- Integrated Business Handler + real Postgres Store adapter with one transaction covering Nonce, Receipt, business state, Transition and Outbox.
- Tenant RLS/forced isolation, dedicated non-owner runtime role, catalog-level grants and negative-role tests.
- Outbox relay, consumer deduplication and crash/restart recovery.
- Ambiguous COMMIT fault injection with persisted-state snapshots and read-only reconciliation.
- Signed/approved retry policy distribution and durable policy-version persistence.
- Formal owner/security sign-off for remaining DEC-03/DEC-14/DEC-16/DEC-19/DEC-30 decisions.

Product Code Freeze remains active. This batch does not authorize production Business Handler rollout or PR merge.
