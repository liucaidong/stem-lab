# Cross-Document Architecture and Contract Consistency Audit

**Version:** 0.1.0  
**Status:** PARTIAL CONSISTENCY REVIEW / ACCEPTANCE BLOCKED  
**As-of:** 2026-11-03  
**Gate:** G14 OPEN

## 1. Documents reviewed

- 00 Baseline and Scope
- 01 Gap Register and Dependencies
- 02 G0–G15 Entry Gate Matrix
- 03 Protocol, Assertion and Digest Source Audit
- 04 Receipt, Idempotency and Nonce Audit
- 05 Atomic UOW and Locking Design
- 06 Action Binding Matrix
- 07 PostgreSQL Security Model Audit
- 08 PostgreSQL Test Strategy
- 09 Complete Vertical Slice Design
- 10 Remaining Action Designs
- 11 Architecture Decision and Deferred Register
- 12 Pre-Implementation Risk Register
- PR #20 source audit and relevant PR #13/#14/#15/#18/#19 source assets.

## 2. Consistency checks

| Check | Result | Notes |
|---|---|---|
| Scope boundary | PASS | All documents remain pre-implementation design/audit; no Handler implementation or production UOW is included |
| PR #13 immutability | PASS for PR #21 diff | PR #21 changed-file list contains only new documentation under the pre-implementation directory |
| Legacy compatibility | PASS as a constraint; proof OPEN | All documents prohibit changing v1alpha1/v2alpha1 behavior; complete regression matrix remains required |
| Digest/mutation binding | CONSISTENTLY BLOCKED | Every relevant document treats same typed binding as mandatory and not yet implemented |
| Receipt semantics | CONSISTENTLY OPEN | Same-key business retry preserves the Request Envelope/digest but re-issues a fresh assertion nonce; exact old assertion replay is rejected; current fixture identity defect is explicitly recorded |
| Nonce semantics | CONSISTENTLY OPEN | Legacy ledger is not represented as v2alpha2 integration; cross-version policy remains unresolved |
| Atomic UOW | CONSISTENTLY PROPOSED | Mutating write set belongs to one outer transaction; exact per-action mutation/lock order remains open |
| Lock order | OPEN | No document promotes PR #20's candidate order to accepted normative rule |
| SQL security | CONSISTENTLY OPEN | No production SECURITY DEFINER or role split is approved; no Runtime privilege widening |
| Failure semantics | CONSISTENTLY PROPOSED | Infrastructure/write-set errors abort whole outer transaction; terminal business failure semantics still open |
| Test evidence boundaries | PASS | Helper-level CI is never treated as Handler/UOW or production readiness proof |
| DLQ Replay scope | OPEN / EXPLICITLY DEFERRED | Existing digest map contains replay, but requested action list does not; no silent scope expansion |
| Production decisions | PASS as deferred constraints | DEC-03/DEC-14 and production Store/Driver/Pool/provider remain unselected |
| Product freeze | PASS as preserved constraint | ACTIVE; P3.17 out of scope; no implementation authorization |

## 3. Contradictions and decisions still requiring closure

### C-01 — Receipt and Nonce ordering

The candidate Job UOW sequence places Receipt reservation before Nonce consumption, but the definitive order is not accepted. It must be proven against same-key contention, same-operation conflict, nonce reuse and rollback. No document should treat this ordering as normative before G8.

### C-02 — Terminal failure versus transaction abort

A business terminal failure may need a committed failed Receipt and failure transition; a database/write-set failure must abort the entire transaction. The current Receipt status model alone does not distinguish these cases. A typed business outcome versus infrastructure abort contract is required.

### C-03 — Renew and Outbox Receipt policy

The digest schema supports Receipt/Nonce patterns, but whether every Renew/Dispatch/Ack action must create a Receipt is not decided. Avoid assuming all actions share the same write set.

### C-04 — Complete Session mutation

The Complete digest args include expected_session_revision and result_ref, but the authoritative storage location and revision update semantics for result_ref are not confirmed by the current source audit. This must be resolved against the Session domain model before SQL mutation design.

### C-05 — Key revocation race

Signature verification may happen before transaction start, while key revocation can change concurrently. Decide whether key state is revalidated inside the transaction, captured by a signed trust snapshot, or governed by an accepted bounded staleness rule.

### C-06 — Nonce durability policy

If nonce insertion rolls back with the entire UOW, the assertion can be retried after a failed attempt; this is often desirable for atomic retry but differs from a permanently consumed anti-replay token policy. The security semantics must be explicit and tested.

### C-07 — SQL file cleanliness

The digest test harness parses each declared function body separately and ignores trailing orphan fragments. The complete SQL asset must be cleaned and validated as a whole before it is considered a stable source artifact.

### C-08 — Assertion replay versus business idempotency

The upstream R03.52.7.3.5 contract is explicit: a committed nonce collision is rejected; the Receipt must not override that authorization failure. The supported client retry is a new assertion (fresh nonce/iat/exp/signature) over the same immutable business Request Envelope and digest. A fresh assertion may then resolve the existing Receipt without repeating the mutation. Any statement that an exact old signed assertion returns a Receipt is inconsistent and must be removed.

### C-09 — Retry-policy authority and unit mismatch

The v2alpha2 Fail/Retry digest arguments include retryability and delay values, while R03.52.4 defines those values as outputs of a versioned policy registry based on error code and persisted attempt budget. The registry schema/runtime has no global maximum delay, and the sample policy is illustrative. Fail uses integer microseconds, Retry uses integer seconds, and the legacy Store API uses floating-point seconds. No accepted rule currently establishes who computes these values, which policy version is pinned, or the exact conversion/rounding/bounds. G1/G4/G13 remain OPEN until the same policy result is bound to digest and mutation.

## 4. No implicit acceptance

This cross-audit is not an independent Security approval. It records consistency of the documents and explicitly retains the unresolved issues above. No proposal becomes ACCEPTED by being repeated in multiple documents.

## 5. Gate conclusion

G14 remains OPEN. A second independent review is required after C-01 through C-07 are resolved and the updated contracts/test evidence are committed.

## Change history

- 2026-11-03: Initial cross-document consistency review.
