# Protocol, Assertion and Digest Source Audit

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / CONTRACT NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gate:** G1 OPEN

## 1. Audited assets

- `contracts/worker-resource-assertion.schema.v2alpha2.json`, blob `c19435be682375ab8b682fa475a3055666337f00`
- `runtime/request_digest_v2alpha2.py`, blob `17f905ef1bd1c31f4dd4094600b5ecb7bdea069e`
- `sql/request-digest-v2alpha2.sql`, blob `c12980e0dc425e603046a81665b26f9eecb7006d`
- PR #20 source audit, commit `a9394870164bba5971ffa82b15c83d7e9b9cfc47`

These are candidate/conformance assets. Their presence does not freeze the protocol or approve a production verifier.

## 2. Observed Claim and Envelope

The v2alpha2 JSON Schema requires `v`, `contract_version`, `iss`, `kid`, `tenant_id`, `sub`, `aud`, `action`, `job_id`, `resource_type`, `resource_id`, `session_id`, `owner`, `epoch`, `operation_id`, `idempotency_key`, `request_digest`, `iat`, `exp`, and `nonce`.

The schema uses numeric `v=2` plus `contract_version="2alpha2"` to distinguish this contract from v2alpha1. The current action enum also includes `worker.dlq.replay`, beyond the eight action families named in this closure task. That scope difference must be decided explicitly.

The Request Envelope is separately composed of `contract_version`, `action`, `tenant_id`, `job_id`, `session_id`, `resource_type`, `resource_id`, `operation_id`, `idempotency_key`, and `operation_arguments`. Issuer/key/time/subject/owner/epoch/nonce/request_digest are Claim fields, not fields in the current canonical Request Envelope.

## 3. Typed encoding observed

The Python and PostgreSQL helpers encode null, booleans, signed int64, UTF-8 strings, arrays and objects with explicit type tags and length/count prefixes. Object keys are sorted by UTF-8 bytes; array order is retained. The envelope has domain separator `STEMLAB-REQUEST-DIGEST\0v2alpha2\0`; identity fields use fixed field order; the operation-arguments object uses recursive typed encoding. SHA-256 is rendered as lowercase `sha256:<64 hex>`.

Python rejects floating-point values and out-of-range integers. PostgreSQL checks integer numeric scale and signed-int64 bounds. Golden vectors exist for ASCII and Unicode in PR #15.

## 4. Verifier path observed

The SQL verifier accepts payload Base64URL, signature Base64URL and a separately supplied `p_operation_arguments`. It bounds payload/signature sizes, checks canonical Base64URL round-trip in the complete verifier definition, parses original UTF-8 JSON before jsonb conversion, rejects unknown/missing Claim fields, validates version/time/nonce/digest, resolves an issuer key matching issuer and kid with validity/revocation predicates, verifies Ed25519 over the exact decoded payload bytes, then recomputes the digest using the separately supplied operation arguments.

The strict parser recursively rejects duplicate object members, including nested objects and objects inside arrays, and bounds payload size/depth.

## 5. Critical digest-to-mutation binding gap

**FACT:** the verifier accepts operation arguments independently from Claim identity and returns a Claim. The audited source does not prove that the exact typed values used to recompute the digest are the same values later used by business SQL UPDATE/INSERT statements.

**Required invariant:** each Handler derives one immutable typed operation binding from the verified Claim plus validated operation inputs. It uses that binding both to construct the digest projection and to execute every mutation. Tenant, Job, Session, Owner, Epoch, Action, Resource Type and Resource ID cannot be re-supplied as a second independently trusted parameter set after verification.

```text
verified_claim = verify(raw_assertion)
typed_binding = bind_action_arguments(verified_claim, raw_operation_inputs)
assert_digest(verified_claim, typed_binding.digest_projection)
mutate_using(typed_binding.mutation_projection)
```

Digest and mutation projections may differ only where an action-specific contract explicitly defines and tests their equivalence. No caller-controlled JSON object may be passed independently to the digest verifier while unrelated SQL parameters drive the mutation.

## 6. Source-level discrepancies

| ID | Observation | Required closure |
|---|---|---|
| PROTO-01 | JSON Schema caps many Claim strings (issuer/key/tenant/subject/audience etc.); SQL verifier string loop checks string/non-empty for most fields but does not show equivalent per-field maximums | Normative field table and SQL/Python/Schema equivalence tests |
| PROTO-02 | Schema caps epoch/iat/exp at 2^53−1; SQL verifier checks integer/non-negative values but does not show the same explicit upper bound | Align numeric limits and every consumer cast |
| PROTO-03 | Python identifier regex rejects C0 and DEL; SQL envelope validator uses POSIX control-class rejection | Cross-language C0/C1 Unicode negative vectors |
| PROTO-04 | Fetched 573-line SQL asset contains six function declarations but nine `$fn$;` terminators; three trailing repeated function bodies begin with orphaned `THEN` fragments | Remove orphan fragments; test the complete SQL file parses as a standalone asset |
| PROTO-05 | Action map includes `worker.dlq.replay`, while this task's Handler matrix names eight action families and omits replay | Explicitly defer or add replay contract; no silent scope expansion |
| PROTO-06 | Digest helper accepts a separate operation-arguments object | Handler-level same-value binding and substitution tests |
| PROTO-07 | Issuer-key lookup is only a disposable fixture table, not a trusted production issuer/key lifecycle | G3 signer provenance, rotation, revocation and key access design |

PROTO-04 is a direct source observation. The current test script splits the SQL file on `CREATE OR REPLACE FUNCTION` and extracts each body only through the first `$fn$;` terminator. This allows the harness to ignore malformed trailing fragments; it does not make the complete SQL asset valid as a standalone script.

## 7. Normative questions still OPEN

1. Is the exact digest domain separator and field order approved, or is R535-OD3 still awaiting approval? The current decision register says OPEN.
2. Are strings Unicode-normalized? Current code encodes raw UTF-8 without normalization; do not add normalization without a versioned decision.
3. Are all JSON numbers integer-only? The typed codec is integer-only; align schema and handler parameter types.
4. What are null semantics for every action argument?
5. What are normative limits for string bytes, object/array counts, total canonical bytes and Claim string lengths?
6. What is the stable error taxonomy for malformed Base64URL, UTF-8, duplicate keys, key state, signature and digest mismatch?
7. Does each action's resource_id bind to the exact persisted resource locked and mutated?

## 8. Required G1 acceptance tests

- Raw-payload signature coverage; duplicate keys top-level/nested/array-contained.
- Invalid UTF-8/JSON/non-object, unknown/missing/null/wrong-type fields.
- Base64URL padding, alphabet, malformed lengths and noncanonical pad bits.
- Epoch/iat/exp boundaries, int64/safe-integer limits, expiry and maximum validity.
- Unicode normalization policy, supplementary characters, C0/C1 controls and unpaired surrogates.
- Integer boundaries, negative values, -0, decimal/exponent notation, floats and huge integers.
- Array/object order, nesting depth and member/element limits.
- Cross-language Python/PostgreSQL golden bytes and digest equality.
- For every action, mutate each parameter after digest construction and prove rejection before durable mutation.
- Unknown Claim/Envelope/action argument fields are never ignored.

## 9. Gate conclusion

G1 remains OPEN. Existing assets are useful candidate primitives, but they do not establish a fully approved protocol, complete cross-language boundary equivalence, or binding between digest input and business mutation values.

## Change history

- 2026-11-03: Initial source audit against PR #20 branch source blobs.
