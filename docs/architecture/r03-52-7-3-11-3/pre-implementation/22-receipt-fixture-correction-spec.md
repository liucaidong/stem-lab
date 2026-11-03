# Receipt Test Fixture Correction and Acceptance Vectors

**Version:** 0.1.0  
**Status:** TEST CORRECTION SPECIFICATION / NOT IMPLEMENTED  
**As-of:** 2026-11-03  
**Gates:** G5/G11 OPEN

## 1. Current defect

The PR #19 PostgreSQL fixture uses a fixed literal digest while changing operation_id in replay and concurrent-first-use scenarios. The Request Envelope includes operation_id and idempotency_key, so those test cases do not represent the same signed operation.

The Receipt helper does not calculate the digest itself; it trusts a syntactically valid digest argument. Therefore helper-level tests must generate digest values from the exact identity tuple or explicitly label a test as testing arbitrary helper input only.

## 2. Canonical fixture builder

Tests should create a Request Envelope fixture first, then derive the digest from it. Never hand-copy a digest into a second fixture after changing any digest-covered field.

Required helper interface (test-only concept):
- build_envelope(contract_version, action, tenant_id, job_id, session_id, resource_type, resource_id, operation_id, idempotency_key, operation_arguments)
- encode_canonical(envelope)
- digest(envelope) -> sha256:hex
- build_claim(envelope, digest, issuer, kid, subject, audience, owner, epoch, iat, exp, nonce)
- sign_exact_payload(claim_bytes)

Every test should retain the envelope alongside its digest and assertion.

## 3. Corrected acceptance vectors

### V1 — Same logical request re-issued with a fresh assertion nonce

First request:
- tenant = tenant-a
- action = worker.job.complete
- idempotency_key = key-replay
- operation_id = operation-1
- resource_type/resource_id = job/job-1
- args = exact Complete args
- digest = recomputed digest A
- assertion nonce = nonce-A

Retry/re-issuance:
- the entire business Request Envelope remains identical, including operation_id, idempotency_key and operation_arguments;
- digest remains digest A because nonce/iat/exp/signature are not Request Envelope fields;
- assertion uses a fresh nonce-B, fresh iat/exp and a new signature over the new Claim payload;
- expected: same Receipt ID, created=false, stored terminal outcome; nonce-B is consumed in the same transaction; no second business mutation.

### V2 — Exact old assertion replay

Submit the exact original signed payload and nonce-A again in a new transaction after nonce-A was committed.

Expected: reject as ASSERTION_REPLAYED (or the explicitly approved read-only replay response), never execute a second mutation. This is not the canonical client retry path.

### V3 — Same idempotency key, different digest

First request uses key-conflict, operation-1, digest A.

Second request uses:
- same tenant/action/idempotency_key;
- a new operation_id or changed operation_arguments;
- recomputed digest B from the complete changed envelope.

Expected: IDEMPOTENCY_CONFLICT; existing Receipt unchanged; no Job/Session/Nonce/Transition/Outbox mutation.

### V4 — Same operation ID, different idempotency key

First request uses operation-unique-1 and key-one, digest A.

Second request uses:
- same tenant and operation_id;
- different idempotency_key;
- recomputed digest C because idempotency_key is part of the envelope.

Expected: OPERATION_ID_CONFLICT; no second Receipt or business mutation.

### V5 — Concurrent same logical request, fresh nonces

Two independent connections submit the same business Request Envelope, same operation_id, same idempotency_key and same digest, but each has a distinct fresh assertion nonce and signature.

Expected:
- exactly one Receipt row;
- one caller performs the business mutation;
- the other observes the same terminal Receipt after arbitration;
- both fresh nonces are consumed if both assertions are valid and accepted under the re-issuance policy;
- both return the same Receipt ID/outcome;
- exactly one Job/Session/Transition/Outbox effect after integrated UOW is tested.

### V6 — Concurrent same key, different envelope

Two connections submit the same tenant/action/idempotency_key but different operation_id or arguments, each with its own correctly recomputed digest.

Expected:
- one request wins the unique key;
- loser observes IDEMPOTENCY_CONFLICT after winner commits;
- no loser business mutation;
- outcome is deterministic regardless of scheduling.

### V7 — Digest/identity substitution

Pass the digest from envelope A alongside a Receipt reserve call whose operation_id or resource identity comes from envelope B.

Expected at the integrated Handler boundary: reject before durable Receipt/Nonce/business mutation. The Receipt helper alone cannot prove this because it does not recompute the digest.

## 4. Distinguish helper tests from integrated tests

| Test level | May pass arbitrary syntactically valid digest? | Required evidence |
|---|---|---|
| Receipt helper unit/conformance | Yes, if explicitly testing only helper arbitration and no claim is made about digest correctness | Documented helper-only scope |
| Digest verifier | No; must recompute from complete envelope and typed args | Golden vectors + signature + digest checks |
| Handler integration | No; digest must be derived from exact mutation binding | Same typed local values used for digest and SQL |
| Full UOW | No; same identity/digest flows through Receipt, Nonce and all business writes | Full persisted-state snapshots and replay proof |

## 5. Additional negative cases

- same idempotency key, different action;
- same key, different tenant;
- same operation ID across different tenants (allowed or denied per tenant scope, must be explicit);
- same operation ID across different actions in same tenant;
- same digest with different idempotency key (should not be generated as a valid vector because key is digest-covered);
- changed resource_id with original digest;
- changed operation_arguments with original digest;
- null/empty/oversized identity fields;
- terminal Receipt replay with mismatched stored outcome;
- pending Receipt replay and recovery;
- rollback after reservation, nonce consumption, Job mutation, Transition insert, Outbox insert and finalization.

## 6. Acceptance criteria

- All fixture digests are generated from the exact canonical envelope.
- No test changes operation_id/idempotency_key/resource/arguments while reusing the original digest.
- Same-request replay preserves the entire signed payload and nonce.
- Different-envelope conflict tests recompute the digest and sign the new payload.
- Handler tests prove the Receipt helper receives values from the verified typed binding.
- UOW tests prove one durable business effect despite concurrent identical submissions.

## 7. Gate conclusion

G5 and G11 remain OPEN until PR #19 fixture corrections are committed in a separately reviewed test change and the integrated Handler tests pass. This document does not modify PR #19.

## Change history

- 2026-11-03: Initial Receipt fixture correction specification.
