# v2alpha2 Claim Validation Parity Matrix

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / PARITY NOT PROVEN  
**As-of:** 2026-11-03  
**Gate:** G1 OPEN

## 1. Audited implementations

- JSON Schema: contracts/worker-resource-assertion.schema.v2alpha2.json
- PostgreSQL verifier: sql/request-digest-v2alpha2.sql, active verifier definition at the first complete verify_request_assertion_v2alpha2 body
- Python digest codec: runtime/request_digest_v2alpha2.py
- PostgreSQL test harness: scripts/test_postgres_request_digest_v2alpha2.py

The Python module validates canonical Request Envelope/action arguments; it is not a complete v2alpha2 Claim validator. The PostgreSQL verifier performs manual Claim checks. The JSON Schema is a separate validation artifact. The current tests do not prove all three implementations enforce identical Claim constraints.

## 2. Field parity matrix

| Claim field | JSON Schema | SQL verifier observed | Parity |
|---|---|---|---|
| v | const integer 2 | JSON number and text equals 2 | Partial; exponent/decimal representations need explicit vectors |
| contract_version | const string 2alpha2 | string field loop + equals 2alpha2 | Partial; explicit type/length implicit in exact value |
| iss | non-empty string, max 256 | non-empty string only | Mismatch: no max 256 shown |
| kid | non-empty string, max 128 | non-empty string only | Mismatch: no max 128 shown |
| tenant_id | non-empty string, max 256 | non-empty string only | Mismatch |
| sub | non-empty string, max 256 | non-empty string only | Mismatch |
| aud | non-empty string, max 256 | non-empty string only | Mismatch |
| action | closed enum of nine action names | non-empty string in verifier; closed action/resource map enforced by digest helper | Split validation; direct verifier alone does not prove exact enum |
| job_id | non-empty string, max 256 | non-empty string only | Mismatch |
| session_id | non-empty string, max 256 | non-empty string only | Mismatch |
| owner | non-empty string, max 256 | non-empty string only | Mismatch |
| epoch | integer min 1, max 9007199254740991 | numeric integral, >=1, later cast to bigint; no same explicit max | Mismatch |
| operation_id | non-empty string, max 256 | non-empty string only | Mismatch |
| idempotency_key | non-empty string, max 256 | non-empty string only | Mismatch |
| request_digest | sha256: + 64 lowercase hex | same regex | Match |
| iat | integer min 0, no JSON Schema max | numeric integral, >=0, cast to bigint | Range/error mismatch possible |
| exp | integer min 1, no JSON Schema max | numeric integral, >=1, cast to bigint | Range/error mismatch possible |
| nonce | string 16..256, Base64URL alphabet | same length and alphabet | Match |
| resource_type | closed enum job/dlq_item/outbox_event/receipt | validated through action/resource map in digest helper | Split validation |
| resource_id | non-empty string, max 256 | envelope validator applies bounded identifier rule when digest is built | Depends on helper invocation; verifier alone does not validate max |

## 3. Other parity gaps

- SQL uses bigint casts for epoch/iat/exp; a JSON numeric value outside bigint range may produce a database cast error instead of the documented stable invalid-claim error.
- The canonicalization ADR specifies signed int64 for typed integer values and max safe integer for Claim epoch. Schema currently uses a safe-integer maximum only for epoch; iat/exp have no explicit upper bound.
- SQL verifier string loop validates non-empty values, but several fields rely on downstream digest/action mapping for additional checks.
- Python module's strict Request Envelope validation does not substitute for a Claim validator; it must not be cited as evidence of Claim field parity.
- Error mapping for a SQL numeric overflow/cast failure is not normalized in the current helper.

## 4. Recommended normative correction

1. Publish one Claim field table containing JSON type, requiredness, max UTF-8 bytes/code points, character policy, numeric bounds and error code.
2. Prefer explicit safe numeric bounds for all timestamp/epoch fields that are represented in JavaScript-compatible JSON numbers; if the protocol chooses signed int64 instead, ensure every serializer/parser preserves exact integer values.
3. Enforce identical limits in JSON Schema, Python Claim validator and SQL verifier.
4. Ensure action/resource closed mapping is checked before digest or mutation.
5. Normalize all malformed/range errors into stable verifier error classes without swallowing transaction errors.
6. Add boundary vectors at max, max+1, min, min-1, bigint overflow, and very long strings for each field.
7. Ensure no implementation accepts an unknown field that another rejects.

## 5. Required parity tests

- For every Claim field: absent, null, wrong type, empty, max valid, max+1.
- Numeric values: 1, 1.0, 1e0, -0, max safe integer, max safe + 1, bigint max, bigint max + 1.
- Unicode strings: ASCII, supplementary plane, C0/C1 controls, combining characters, unpaired surrogate representation and invalid UTF-8.
- All nine actions with valid/invalid resource_type/resource_id combinations.
- Unknown action, unknown resource type, action-resource mismatch.
- Compare JSON Schema validator, Python Claim validator and PostgreSQL verifier outcomes for the same corpus.

## 6. Gate conclusion

G1 remains OPEN. The current schema, SQL verifier and Python codec have overlapping but not proven-identical validation boundaries. The mismatch must be resolved before protocol acceptance.

## Change history

- 2026-11-03: Initial Claim validation parity matrix.
