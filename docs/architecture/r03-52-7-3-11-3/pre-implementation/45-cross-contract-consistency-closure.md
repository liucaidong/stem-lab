# R03.52.7.3.11.6 — Cross-Contract Consistency Closure

## Purpose

This delta closes inconsistencies exposed while integrating the first v2alpha2 Business Handler slice. The reference implementation must not accept a request in one layer and reject, reinterpret, or weaken it in another.

## Normative alignment applied

| Concern | Python reference | JSON Schema | PostgreSQL | Acceptance |
|---|---|---|---|---|
| `worker.job.fail` arguments | Includes `retry_policy_version` and `safe_message` | FailCommand requires `request_digest` and policy version | Exact argument set and types checked | Python + PostgreSQL positive/negative cases |
| Idempotent failure write | FailJobCommand carries request digest | Digest is required and SHA-256 formatted | Digest remains bound to signed assertion and canonical arguments | Store contract tests |
| Stable error code | Uppercase ASCII token, 1–64 chars | Same | Same regex | Retry and request digest tests |
| Retry policy version | 1–128 chars | 1–128 chars | 1–128 chars | Python + PostgreSQL tests |
| Safe message | 1–512 chars | 1–512 chars | 1–512 chars | Python + PostgreSQL tests |
| Retry attempts | 1–100 | Maximum 100 | Persisted Job remains authoritative | Runtime and registry tests |
| Lease epoch | Positive JSON-safe integer | Maximum 9007199254740991 | Claim verifier enforces same safe-integer ceiling | Runtime/store tests |
| Session revision | 0–2147483646 | Same | Same | Request Digest tests |
| Job lease renewal | Integer seconds, 5–300 | Request Digest contract | Same | Python + PostgreSQL |
| Outbox dispatch lease | Integer seconds, 5–3600 | Request Digest contract | Same | Python + PostgreSQL |

## Retry authority

WorkerRuntime now rejects arbitrary RetryPolicyProvider implementations and requires the concrete immutable RetryPolicyRegistry. The exception classifier can only produce a stable error code; retryability, delay and policy version remain registry-derived. Unknown codes continue to map to the non-retryable default.

## Transaction and persistence boundary

These changes strengthen reference contracts and test coverage. They do not add Job fail/retry/renew/dead-letter SQL handlers, do not migrate production data, and do not prove production key management, role grants, retention, monitoring or deployment safety. The first executable atomic handler remains limited to `worker.job.complete` for `package.validate`.

## Required CI evidence

- Python Store Protocol, Worker Runtime, Retry Policy and Request Digest tests.
- Complete Request Digest SQL asset execution on PostgreSQL 17.11 with pgsodium.
- Positive and negative PostgreSQL `worker.job.fail` canonical argument tests.
- Existing atomic Business Handler/UOW PostgreSQL tests.

A green CI run is necessary but not sufficient for merge or production readiness. Independent review and owner/security approvals remain mandatory.
