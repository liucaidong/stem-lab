# Re-Issued Assertion, Nonce Consumption and Receipt Reconciliation Semantics

**Version:** 0.1.0  
**Status:** SOURCE-DERIVED DESIGN CLARIFICATION / CONTRACT NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gates:** G5/G6/G10 OPEN

## 1. Existing upstream contract evidence

R03.52.7.3.5 Section 8 explicitly distinguishes:
- assertion replay: same signed token submitted again; reject as a new transaction after committed nonce use;
- reuse inside one transaction: same token may authorize multiple statements in one UOW;
- reuse across transactions: deny after committed nonce use;
- client retry: new assertion nonce, same business idempotency key/digest;
- idempotent request replay: same operation key and same digest returns original durable outcome without duplicate effects;
- idempotency conflict: same key, different digest rejects;
- ambiguous commit: reconcile by durable operation Receipt, do not blindly replay.

It also states that nonce consumption and protected business writes commit atomically, while business idempotency survives assertion re-issuance. This is important source evidence and refines the simpler exact-token replay model.

## 2. Three distinct retry/replay paths

### Path A — Exact same assertion replay

Same payload bytes, signature, nonce, operation_id, idempotency_key and request_digest are submitted again in a new transaction after the first transaction committed.

Expected:
- signature and claim scope can be revalidated;
- Receipt lookup must identify the exact same business operation;
- committed nonce already exists;
- the token must not authorize a second mutation;
- returning a previously committed terminal Receipt may be permitted as a read-only replay response only if the action contract explicitly allows it; otherwise return ASSERTION_REPLAYED.
- no Job/Session/Transition/Outbox side effect is repeated.

This path is not the normal client retry mechanism.

### Path B — Client re-issues the same business request

The client retains the same logical Request Envelope:
- same tenant/action/resource;
- same operation_id;
- same idempotency_key;
- same operation_arguments;
- same request_digest.

It receives a fresh assertion:
- new nonce;
- new iat/exp;
- new signature over the new exact Claim payload.

Expected:
- new nonce is consumed in the same transaction as the attempted protected operation/replay resolution;
- Receipt arbitration finds the same tenant/action/idempotency key and same digest;
- if a terminal Receipt exists, return the stored outcome and do not repeat Job/Session/Transition/Outbox effects;
- if no Receipt exists, the request may proceed once under the same immutable business identity;
- a same key with different digest is IDEMPOTENCY_CONFLICT;
- a reused nonce is rejected even if the business idempotency key matches.

This is the canonical retry path described by R03.52.7.3.5.

### Path C — Ambiguous commit reconciliation

After a connection loss during COMMIT, the client must not assume rollback and must not replay the old assertion nonce in a new transaction.

Expected:
- issue a fresh narrowly scoped reconciliation assertion with a fresh nonce;
- retain the stable logical operation_id and idempotency identity;
- query the durable Receipt/result ledger;
- if a matching terminal Receipt exists, return its original outcome;
- if the key exists with another digest, return IDEMPOTENCY_CONFLICT;
- if no committed Receipt exists, retry the original business action using a fresh nonce but the same business idempotency key and original request_digest;
- if state cannot be established, preserve TRANSACTION_OUTCOME_UNKNOWN.

## 3. Nonce lifecycle consequences

- Nonce uniqueness remains independent of business idempotency.
- A new assertion nonce for the same business request creates a new nonce-ledger row, but not a new business operation.
- A repeated nonce across transactions is rejected.
- Multiple fresh nonces may be associated with one stable operation_id/digest as re-issuances; the ledger must retain enough metadata to correlate them.
- Nonce insertion belongs to the same transaction as the action or reconciliation read boundary. A rollback removes that attempt's nonce consumption.
- Do not insert the nonce in a separately committed transaction before Receipt arbitration/business mutation.
- Retention must cover assertion expiry, clock skew, transaction recovery and investigation windows; exact duration remains OPEN (R535-OD4).

## 4. Receipt reconciliation identity ambiguity

Current v2alpha2 digest helper maps Receipt Reconcile to:
- action = worker.receipt.reconcile;
- resource_type = receipt;
- resource_id must equal operation_id;
- operation_arguments = empty object.

The upstream R03.52.7.3.5 contract says a fresh reconciliation assertion is issued for the same subject/tenant/Job/Session and operation ID, then the durable Receipt is read by stable idempotency key and its canonical request digest is checked.

This leaves a semantic ambiguity:
- Is Claim.operation_id the original stable business operation ID being reconciled, or a new reconciliation command ID?
- Is Claim.request_digest the digest of the reconciliation envelope or the original business request?
- How does the reconcile handler obtain/verify the original digest when action=receipt.reconcile has an empty argument object?
- Does reconcile consume a new nonce but create no new Receipt, or does it create a distinct Receipt for the reconciliation command?

**Recommended resolution:** preserve operation_id as the stable logical business operation ID and resource_id as the target Receipt operation ID for the current candidate contract. Treat Receipt Reconcile as a read-only lookup action that creates no new business Receipt. Its own assertion digest authenticates the reconcile action envelope; the target Receipt's stored original request_digest is independently checked against the Receipt's stored identity and idempotency record. If the API needs a separate reconciliation command ID or caller-supplied expected original digest, add it explicitly to a versioned action-specific contract; do not overload operation_id or compare unlike digests.

The precise mapping of original action/idempotency key to target Receipt must be written into the action contract before implementation.

## 5. Required acceptance vectors

- Exact old assertion replay after committed nonce: no second mutation; defined read-only replay result.
- Same logical request with fresh nonce: Receipt returns stored outcome; nonce row for fresh assertion commits; no second mutation.
- Same business key with changed args and recomputed digest: IDEMPOTENCY_CONFLICT.
- Same business key with changed args but old digest: reject at digest verifier before Receipt mutation.
- Same nonce with changed signature/time/arguments: reject as nonce replay or digest/signature mismatch.
- Fresh reconciliation nonce, same stable operation_id: read existing Receipt and return its original outcome.
- Reconciliation with mismatched target idempotency key/digest: reject.
- No Receipt + fresh assertion nonce: retry original action only with original request envelope/digest; do not mutate from a reconciliation envelope.
- Ambiguous commit with a committed Receipt: return original outcome.
- Ambiguous commit with no committed Receipt: retry once with fresh nonce and same business identity.

## 6. Gate conclusion

G5 and G6 remain OPEN. This clarification aligns the audit with R03.52.7.3.5's explicit distinction between assertion replay and client retry, but the Receipt Reconcile digest/identity mapping still requires an accepted contract.

## Change history

- 2026-11-03: Initial re-issued assertion and nonce clarification.
