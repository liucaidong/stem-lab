# Retry Policy Authority, Action Binding and Delay Unit Audit

**Version:** 0.1.0  
**Status:** SOURCE-VERIFIED GAP / POLICY DECISION NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gates:** G1 / G4 / G13 OPEN

## 1. Purpose

This audit compares the existing Worker Retry Policy Registry (R03.52.4) with the v2alpha2 Request Digest action argument contract and the legacy Store protocol. It does not choose a production policy, change existing behavior or authorize Handler implementation.

## 2. Source inventory

| Source | Verified contract | Boundary |
|---|---|---|
| `runtime/retry_policy.py` | RetryPolicy uses `base_delay_seconds` and `max_delay_seconds` as floats; values must be finite/non-negative; max must be >= base; non-retryable policies must have zero bounds; decision uses persisted attempt_count/maximum_attempts and full jitter | Reference policy evaluator, not a production classifier or approved catalog |
| `contracts/worker-retry-policy.schema.v1alpha1.json` | Delay fields are JSON numbers with minimum 0; no absolute maximum is defined | Schema validation does not establish a global delay cap |
| `contracts/worker-retry-policy.v1alpha1.json` | Illustrative sample uses 120 seconds for DEPENDENCY_UNAVAILABLE and 300 seconds for RATE_LIMITED | Sample is explicitly illustrative, not approved production policy |
| `runtime/request_digest_v2alpha2.py` | Fail args: error_code/retryable/retry_delay_micros/safe_message; Retry args: delay_seconds/error_code; Retry delay 1..86400 seconds; Fail delay non-negative signed int64; error_code regex | Codec validates shape/range, not whether policy output is authoritative |
| `sql/request-digest-v2alpha2.sql` | Mirrors the Fail/Retry action field sets; Fail checks delay is an integral non-negative number and retryable is boolean; Retry delay is integral 1..86400 | No Fail delay upper bound or retryable/delay cross-field rule is present in the inspected validator |
| `runtime/store_protocol.py` | Legacy Fail command carries `retry_delay_seconds: float` | Legacy API unit differs from v2alpha2 Fail's microseconds |

## 3. Confirmed semantic gaps

### 3.1 Policy output is present in the signed action payload, but policy authority is unspecified

R03.52.4 defines the policy flow:
1. A handler/adapter maps an exception to a stable `error_code`.
2. The registry maps the code to retryability, safe message and delay policy.
3. Persisted `attempt_count` and `maximum_attempts` can disable retry at exhaustion.
4. Delay is calculated from the configured base/max and jitter source.
5. Unknown codes fail closed to a non-retryable default.

The v2alpha2 Fail action instead accepts `retryable`, `retry_delay_micros` and `safe_message` as digest arguments. Retry accepts `delay_seconds` and `error_code`. A valid signature/digest proves that the values match the signed request; it does not prove that those values were correctly derived from the approved policy and persisted attempt budget.

The action contract must identify the trusted policy evaluator and the source of attempt_count/maximum_attempts. A worker-supplied boolean, delay or safe message must not override the policy merely because it is signed.

### 3.2 There is no approved global delay maximum

The Registry JSON Schema constrains delay values to numbers >= 0 but supplies no absolute maximum. The Python dataclass rejects non-finite/negative values and max<base, but has no global ceiling. The sample policy values are examples only. Therefore the current source does not justify a statement that a normative global maximum has already been established.

### 3.3 Units differ across layers

| Layer | Field | Representation |
|---|---|---|
| Retry Policy Registry | base/max/result delay | floating-point seconds |
| Legacy Store Fail | retry_delay_seconds | floating-point seconds |
| v2alpha2 Fail digest | retry_delay_micros | non-negative integer microseconds |
| v2alpha2 Retry digest | delay_seconds | integer seconds, 1..86400 |

No approved conversion contract defines rounding, precision loss, overflow behavior, maximum delay, or whether a sub-second retry is valid. The digest must describe the exact typed value used to derive the persisted scheduling timestamp.

### 3.4 Retry and Fail may duplicate policy decisions

Fail carries policy outputs, while Retry carries a caller-supplied delay and error code. The current sources do not establish whether Fail calculates and schedules a retry directly, or whether it transitions the Job to a state from which a separate Retry command runs. They also do not establish whether both paths invoke the same pinned registry version and attempt budget.

## 4. Recommended closure contract (not approved)

1. Treat `error_code` as a classified input, not as proof of retry policy.
2. Derive retryability, safe message and delay from a versioned, trusted Retry Policy Registry using the persisted Job attempt_count and maximum_attempts under the required Job fence.
3. Pin the policy version (or an immutable policy digest) for the operation so a later registry update cannot change the meaning of a retry already in flight.
4. Do not accept worker/caller-supplied `retryable`, `safe_message` or delay as authoritative. If these fields remain in the signed envelope, the trusted issuer/Handler must calculate and validate them from the pinned policy.
5. Decide whether the digest covers policy inputs, derived outputs, or both; whichever representation is selected must be the same typed binding used by the SQL mutation.
6. Define one canonical internal delay unit and explicit checked conversions at API boundaries. Do not use implicit float/int casts.
7. Define global and per-code maximum delay, immediate-retry semantics, zero-delay semantics, non-retryable delay=0, attempt exhaustion and terminal/DLQ behavior.
8. Align Fail and Retry so the same logical policy decision cannot be reinterpreted by a second caller-controlled delay.

These are recommendations for review, not accepted protocol decisions.

## 5. Required acceptance tests

- Known error code maps to the expected policy and immutable policy version.
- Unknown error code fails closed.
- Attempt count below, at and above maximum_attempts is tested.
- retryable=false always yields zero delay and a safe registry-owned message.
- retryable=true cannot exceed the approved per-code/global ceiling.
- Caller tampering with retryable/delay/safe_message is rejected or recomputed from trusted policy.
- Policy version changes between issuance and execution do not alter the signed operation semantics.
- Seconds-to-microseconds conversion tests cover exact values, sub-second values, rounding, overflow, negative values and maximum accepted delay.
- Fail and Retry calculate/persist the same scheduling instant from the same policy result.
- Digest values are derived from the same typed binding used by the Job update and Transition/Outbox writes.
- terminal_reason=max_attempts/non_retryable is checked against locked persisted attempt state and policy output.

## 6. Decision owners and dependencies

| Decision | Owner | Dependency | Gate |
|---|---|---|---|
| Policy evaluator authority and version pinning | Worker + Protocol + Security | Trusted issuer and Handler binding | G4/G13 |
| Global/per-code bounds | Worker + Product/Operations | Retry policy governance and operational SLO | G4/G13 |
| Canonical delay unit and conversion | Protocol + Database | Existing Store protocol and v2alpha2 schema | G1/G4 |
| Fail vs Retry state transition | Worker + Architecture | Job state machine, attempt budget, DLQ contract | G13 |

## 7. Gate conclusion

G1, G4 and G13 remain OPEN. This source audit exposes a missing authority and units contract; it does not establish a chosen delay unit, policy version or global maximum.

## Change history

- 2026-11-03: Initial Retry Policy authority and delay-unit audit.
