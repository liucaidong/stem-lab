# R03.52.7.3.11.4 — Cross-Module Contract Consistency Matrix

**Status:** SOURCE-VERIFIED DISCREPANCIES / NORMATIVE CONTRACT NOT ACCEPTED  
**Baseline:** PR #20 HEAD `a9394870164bba5971ffa82b15c83d7e9b9cfc47`

## 1. Matrix

| Concern | Python Runtime | Store Protocol | PostgreSQL SQL | Schema / Digest | Finding |
|---|---|---|---|---|---|
| Assertion version | Runtime has separate tenant/v2alpha2 verifier references; no common dispatcher | StoreAccessContext is opaque v1alpha1 contract | v2alpha2 verifier is a separate function | v2alpha1 and v2alpha2 use numeric v=2; v2alpha2 adds contract_version | No common fail-closed dispatcher; no fallback permitted |
| Claim validation | Digest module validates Envelope, not full Claim | N/A | SQL validates closed raw Claim but omits some schema string length limits | v2alpha2 schema caps identity strings and epoch/iat/exp at 2^53-1 | Claim Schema/SQL/Python parity incomplete |
| Signature | No trusted production signer integration | Opaque assertion field only | Ed25519 verifier resolves disposable issuer key | Example issuer/key are test values | Trusted issuer lifecycle and key revocation boundary open |
| Digest identity | Python canonical codec includes operation_id/key/action/resource/args | CompleteJobCommand carries request_digest separately | SQL verifier recomputes from Claim + separately supplied args | Golden vectors cover ASCII/Unicode; R535-OD3 open | Handler must derive digest and mutation from one immutable typed binding |
| Canonical length | `_u32` rejects > 0x7fffffff | No canonical byte budget | `int4send` positive signed-int4 domain | ADR candidate describes uint32 | Narrow implementation range versus ADR; total bytes unbounded |
| Raw JSON | `parse_json_strict` rejects duplicate keys; no explicit input cap | N/A | Raw Claim parser caps 16 KiB and rejects duplicates | Envelope fixture is small; no max Envelope/args budget | Different input surfaces need separate caps |
| Nonce | No v2alpha2 durable nonce ledger call path | Legacy UOW interface has no nonce operation | v2alpha2 verifier checks claim nonce but does not persist it | v2alpha2 schema requires nonce | Exact replay protection not integrated |
| Receipt identity | No v2alpha2 Handler | Store protocol has idempotency key/digest on Complete only | Table unique tenant/action/key and tenant/operation; helper trusts supplied digest | operation_id is part of digest Envelope | Helper must compare exact identity; digest must be recomputed by trusted Handler |
| Receipt Reconcile | No independent v2alpha2 read-only path | No typed missing/pending/terminal/inconsistent result | Only insert-first reserve and finalize functions exist | Action map gives reconcile empty args | Dedicated SELECT-only lookup required; reserve forbidden |
| Receipt privileges | No adapter role evidence | No Receipt-specific role contract | Functions default INVOKER; no explicit revoke/grant/RLS in asset | No catalog schema contract | Runtime privilege boundary unproven |
| Retry authority | WorkerRuntime accepts injected classifier; FailureDecision directly constructible | FailJobCommand accepts caller values and no policy_version | SQL validates basic fields, not trusted policy provenance | Registry has no global maximum | Policy registry not enforced |
| Retry units | Registry float seconds | Legacy Store float seconds, max 86400 | v2alpha2 Fail microseconds; Retry seconds | Digest Fail int64 microseconds; Retry 1..86400 seconds | Unit and ceiling mismatch |
| Error code | Registry/Store allow up to 128 | Store regex 128 | SQL/digest regex 64 for v2alpha2 action args | Registry schema max 128 | Recommend 128 across layers or approve breaking narrowing |
| Safe message | Registry/Store max 512 | Store max 512 | v2alpha2 Fail SQL only checks string type | Digest codec has no matching cap | Enforce 1..512 consistently |
| Result reference | Store max 1024 | CompleteJobCommand max 1024 | SQL requires nonempty string only | Digest codec requires nonempty string only | Align SQL/codec to max 1024 |
| Numeric range | Python typed encoder signed int64 | Store epoch/attempt ints lack common uint declaration | SQL Claim timestamp cast to bigint | Schema max safe integer | Define numeric domain and normalize overflow |
| DLQ Replay | ReplayPlan accepts caller-provided state/counters/actor/reason/new ID/auth | No production replay Store method | Digest action map accepts empty args | R03.52.5 requires reason/request/actor/policy/new Job | Must fail closed until separately bound and authorized |
| Outbox | No v2alpha2 Handler/Relay | Store UOW has no complete outbox dispatch API | Legacy fixture has separate dispatcher path | Digest dispatch/ack args do not carry arbitrary payload | DB Outbox append atomic; relay after commit; at-least-once consumer dedup |

## 2. Recommended normalization (not approved)

1. Keep the existing v1alpha1/v2alpha1 entry points unchanged. Dispatch v2alpha2 only from an explicit discriminator; unsupported actions reject before writes.
2. Use one immutable typed action binding to supply both canonical digest inputs and SQL mutation parameters.
3. Treat nonce as an authorization-instance identifier. Persist it transactionally and check it before Receipt success arbitration.
4. Use a separate SELECT-only Receipt Reconcile query with typed outcomes.
5. Make the policy evaluator authoritative. Add policy_version to the typed signed binding and persist the selected version with the outcome.
6. Normalize retry delay to integer microseconds across v2alpha2 Fail and Retry; convert legacy seconds only at the adapter boundary using Decimal and an explicit rounding rule.
7. Retain 24 hours as a proposed global ceiling to align existing Store/Retry limits; owner approval is required because this is a normative scheduling policy.
8. Align error_code to 1..128 and safe_message to 1..512 across Registry, Store, Digest and SQL, unless the protocol owner explicitly approves a narrower v2alpha2 domain.
9. Align Claim integer timestamps to the JSON Schema safe-integer ceiling (2^53-1); reject out-of-range numeric values before bigint cast and normalize the error.
10. Retain a practical total canonical-byte budget (proposed 1 MiB), an operation_arguments budget (proposed 256 KiB), and the existing 16 KiB Claim ceiling; verify product payload assumptions before approval.
11. Keep the current 4-byte big-endian length prefix but normatively cap accepted positive lengths at 2^31-1, matching the present Python/SQL implementation, and update the ADR accordingly.
12. Keep DLQ Replay outside the first v2alpha2 Handler slice and reject it before any write until its action binding, trusted authorization and atomic UOW are separately accepted.

## 3. Compatibility and migration impact

- v1alpha1/v2alpha1 remain unchanged.
- Adding policy_version and normalizing delay units changes v2alpha2 action binding and golden vectors; version the contract rather than silently reinterpreting existing vectors.
- Increasing error_code from 64 to 128 is widening for v2alpha2; safe_message/result_ref caps require synchronized Python/SQL validation.
- Tightening byte budgets may reject previously accepted oversized inputs; publish exact limits and max/max+1 tests.
- Receipt Reconcile requires a new read-only SQL function or Handler SELECT path; no existing client may use reserve as fallback.
- No production driver, pool, provider or deployment topology is selected here.

## 4. Gate conclusion

G1/G2/G4/G5/G6/G9/G10/G13 remain BLOCKED. The matrix records source discrepancies and recommendations, not an accepted protocol.
