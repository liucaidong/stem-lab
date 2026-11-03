# Action Argument Schema, Bounds and Cross-Field Validation Audit

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / ACTION LIMITS NOT COMPLETE  
**As-of:** 2026-11-03  
**Gates:** G1, G4 OPEN

## 1. Audited source

- PR #15 action argument specification;
- runtime/request_digest_v2alpha2.py validate_envelope;
- sql/request-digest-v2alpha2.sql request_digest_v2alpha2;
- PR #20 business Handler integration source audit.

Python and SQL currently agree on the eight requested action argument names/types at a basic level. However, several strings and numeric values have no business-level upper bound, and some cross-field relationships are not defined.

## 2. Field-level source matrix

| Action | Field | Current Python/SQL rule | Missing or unresolved rule |
|---|---|---|---|
| worker.job.complete | expected_session_revision | non-negative signed int64 | Must match exact Session revision; whether zero valid for all Sessions |
| worker.job.complete | result_ref | string, non-empty | Maximum UTF-8 bytes, identifier syntax, artifact URI/resource ownership and immutability |
| worker.job.fail | error_code | uppercase identifier, 1–64 chars | Closed registry vs regex; whether code is retryable by policy |
| worker.job.fail | retryable | boolean | Must agree with persisted retry policy and terminal attempt count |
| worker.job.fail | retry_delay_micros | non-negative signed int64 | Maximum delay, units conversion, whether non-retryable requires zero |
| worker.job.fail | safe_message | string | Maximum UTF-8 bytes, control-character policy, sanitization/PII rules |
| worker.job.retry | delay_seconds | integer 1–86400 | Whether attempt ceiling and error_code allow retry; DB clock semantics |
| worker.job.retry | error_code | uppercase identifier, 1–64 chars | Closed registry and retryability mapping |
| worker.job.renew | lease_seconds | integer 5–3600 | Per-worker/job policy cap; exact expiry behavior at boundary |
| worker.job.dead_letter | error_code | uppercase identifier, 1–64 chars | Closed registry and source failure provenance |
| worker.job.dead_letter | terminal_reason | enum max_attempts/non_retryable | Must be consistent with persisted attempt count and retry policy |
| worker.outbox.dispatch | lease_seconds | integer 5–3600 | Dispatcher policy cap and event retry/backoff |
| worker.receipt.reconcile | none | empty object | Target Receipt identity semantics and read-only vs repair authority |
| worker.outbox.ack | none | empty object | Meaning of ack and exact dispatch epoch/owner fence |

## 3. Confirmed gaps

1. Python and SQL both accept arbitrary-length result_ref and safe_message strings, subject only to memory/runtime/database practical limits.
2. retry_delay_micros accepts any non-negative signed int64. No action-specific upper bound is shown in the digest validator.
3. expected_session_revision accepts any non-negative signed int64. The persisted Session revision column range and expected bound need to match.
4. retryable and retry_delay_micros are not cross-validated. For example, retryable=false with a positive delay is currently structurally accepted.
5. error_code uses a regex rather than a versioned closed error registry. The repository has a Worker Error Taxonomy and Retry Policy Registry; the action binding must reference the same canonical registry/version.
6. terminal_reason is a closed enum, but no proof is shown that max_attempts/non_retryable matches persisted attempt/error policy.
7. String encoding permits long values up to the generic encoder length limit. The raw Assertion payload limit does not automatically bound separately supplied operation_arguments.
8. The v2alpha2 Fail/Retry payload contains policy outputs (`retryable`, delay, `safe_message`) while R03.52.4 defines these as registry-derived decisions based on error code and persisted attempt budget. No accepted contract identifies the trusted producer, pins a policy version, or prevents a caller from supplying inconsistent outputs.
9. The Retry Policy Registry schema/runtime has no global upper bound for `max_delay_seconds`; the sample 120/300 second values are illustrative only. The current registry is not evidence of an approved maximum or canonical microseconds conversion.
10. The Retry Policy Registry schema/runtime permits error_code up to 128 characters, while the v2alpha2 digest codec accepts only 1–64 uppercase identifier characters; the protocol/registry intersection is not explicitly governed.
11. RetryPolicy safe_message is constrained to 1–512 characters in the Python registry, while the v2alpha2 digest codec/SQL action validator accepts any string length; the digest contract does not currently enforce the registry's message bound.
12. WorkerRuntime accepts an injected `classify_failure` callback and forwards its FailureDecision to Store; it does not enforce RetryPolicyRegistry use. FailureDecision and legacy FailJobCommand carry no policy_version, so the selected policy cannot be independently pinned or audited through the Store call.
13. Delay ceilings differ by boundary: legacy FailJobCommand and v2alpha2 Retry cap at 86,400 seconds, while v2alpha2 Fail accepts non-negative int64 microseconds and the Registry has no global cap. The same policy result can be accepted by one path and rejected or overlarge in another.

## 4. Recommended limits and cross-field rules (proposed)

These are candidate defaults for review, not accepted policy:
- result_ref: non-empty UTF-8 string, <= 256 bytes, must reference an artifact owned by the same tenant/session and immutable after completion.
- safe_message: UTF-8 <= 1024 bytes, reject control characters except explicitly permitted whitespace, redact secrets and credentials before signing.
- error_code: resolve against the canonical versioned Worker Error Taxonomy, not regex alone; align the registry's 128-character limit and v2alpha2 codec's 64-character limit explicitly.
- safe_message: define one UTF-8 byte/code-point limit across the registry, signer, digest codec, SQL and persisted outcome schema.
- retry_delay_micros: do not claim a bound until an approved policy registry version defines one; require exact conversion from the policy result and, if retryable=false, zero delay. If retryable=true, require a policy-authorized bounded delay or a documented immediate-retry value.
- expected_session_revision: non-negative int64 and must be representable by the persisted Session column; require exact equality under lock.
- terminal_reason=max_attempts only when persisted attempt_count >= maximum_attempts; non_retryable only when the accepted error policy classifies the error as non-retryable.
- lease_seconds: retain 5..3600 as codec bounds, then apply any stricter per-job/dispatcher policy inside the locked transaction.

Do not introduce these limits until reconciled with the existing retry policy and result/artifact domain contracts. The trusted issuer/handler must derive retryability, safe_message and delay from the versioned policy using persisted attempt_count/maximum_attempts; caller-supplied values must not become authoritative merely because they are covered by a valid digest. The protocol owner must decide whether the digest binds policy inputs, derived outputs, or both, and how policy version changes affect retries.

## 5. Cross-layer parity tests

For each argument:
- missing, extra, null, wrong type, empty, min, max, max+1, int64 overflow;
- Unicode byte length vs character length;
- control characters and invalid UTF-8;
- same value through Python typed binding and PostgreSQL typed parameters;
- changed value after digest generation;
- cross-field combinations (retryable/delay, terminal_reason/attempt_count, error_code/retryability);
- policy version pinning, unknown error_code fallback, attempt_count/max_attempts boundary, safe_message provenance and registry-derived output tampering;
- exact conversion between policy float seconds, v2alpha2 integer microseconds and Store retry_delay_seconds, including rounding, overflow and maximum delay.
- actual SQL mutation receives the exact same typed value.

## 6. Gate conclusion

G1/G4 remain OPEN. Action argument names and basic types are defined, but length/range/policy and cross-field constraints are incomplete. A generic typed encoder does not substitute for action-specific domain validation.

## Change history

- 2026-11-03: Initial action argument bounds audit.
