# Canonicalization Candidate and PostgreSQL/Python Boundary Audit

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / R535-OD3 OPEN / NOT APPROVED  
**As-of:** 2026-11-03  
**Gate:** G1 OPEN

## 1. Source candidate

The PR #15 canonicalization ADR candidate explicitly recommends Versioned Typed Encoding, conditional on PostgreSQL proof-of-equivalence. It is OPEN / CANDIDATE ONLY / NOT APPROVED.

The candidate defines:
- domain separator STEMLAB-REQUEST-DIGEST + NUL + v2alpha2 + NUL;
- fixed nine-field identity order: contract_version, action, tenant_id, job_id, session_id, resource_type, resource_id, operation_id, idempotency_key;
- typed operation_arguments appended with a J tag and length prefix;
- tags for null, booleans, signed int64, UTF-8 strings, arrays and objects;
- object keys sorted by raw UTF-8 bytes; arrays retain input order;
- nesting depth 32, array/object count 4096, signed int64, uint32 byte lengths;
- rejection of floats, NaN, infinities, invalid UTF-8, unpaired surrogates and duplicate keys;
- no Unicode normalization;
- SHA-256 digest as sha256: plus 64 lowercase hex digits.

The candidate also requires PostgreSQL to receive actual typed function parameters and raw argument representation, not a runtime-provided digest, and to compare the computed digest before nonce insertion or business mutation.

## 2. Python implementation observations

The Python codec:
- uses explicit type tags and length/count prefixes;
- uses signed int64 bounds for integer values;
- uses UTF-8 encoding and UTF-8-byte sorting for object keys;
- preserves array order;
- rejects Python float values;
- validates exact action-specific argument field sets and basic types/ranges;
- uses a 4-byte unsigned big-endian length prefix (struct.pack with unsigned 32-bit format).

It does not provide a full Claim validator; that is separately handled in SQL/schema and currently has parity gaps.

## 3. PostgreSQL implementation observations

The SQL codec:
- uses jsonb for typed values after strict raw Claim parsing;
- sorts object keys by convert_to(key,'UTF8') bytea;
- preserves array ordinality;
- rejects numeric scale other than zero and values outside signed int64;
- uses pg_catalog.int4send for 4-byte network-order lengths/counts;
- explicitly rejects a byte length greater than 2,147,483,647;
- applies depth 32 and array/object count 4096;
- uses SHA-256 from pg_catalog.

The strict parser checks duplicate keys using PostgreSQL json before jsonb conversion and limits raw Claim payload to 16,384 bytes.

## 4. Boundary differences

| ID | Difference | Consequence |
|---|---|---|
| CANON-01 | Candidate ADR specifies uint32 byte lengths; Python uses unsigned 32-bit packing; SQL uses signed int4send and rejects values above 2^31−1 | Bytes are identical only in the common positive range; accepted domain differs |
| CANON-02 | Raw Claim payload is capped at 16 KiB, but operation_arguments is passed separately to digest helper and has no explicit total canonical-byte cap | The Claim cap does not prevent oversized argument payloads or memory/CPU abuse |
| CANON-03 | Action strings such as result_ref and safe_message have no maximum length in Python/SQL action validation | A small Claim can authorize hashing/processing a very large separately supplied argument |
| CANON-04 | Generic codec supports null tag, while current action argument schemas require exact fields and do not permit null | Null must be rejected at action schema layer; codec support is not action permission |
| CANON-05 | Python rejects floats before encoding; PostgreSQL receives jsonb numeric, which may normalize lexical forms before typed validation | Exponent/decimal lexical parity must be tested or avoided by typed SQL parameters |
| CANON-06 | SQL harness extracts function bodies individually up to first $fn$; and does not parse trailing orphan fragments | Full SQL file validity is not established by helper test success |

## 5. Recommended boundary resolution

1. Set an explicit maximum canonical Request Envelope byte length and maximum operation_arguments byte length. A 16 KiB or 64 KiB cap is a candidate; select one based on actual maximum safe_message/result_ref and payload needs.
2. Set per-field UTF-8 byte limits for all action arguments.
3. If all values are capped below 2^31 bytes, explicitly define length prefixes as 4-byte network-order positive lengths with a stricter maximum; alternatively use a truly unsigned uint32 implementation in SQL if larger values are required.
4. Prefer typed SQL parameters for each action argument and construct the canonical argument object from those parameters inside the Handler. Do not rely on a separately supplied JSONB object that can differ from mutation parameters.
5. Reject null for every current action argument unless an action schema explicitly defines null semantics.
6. Test 1, 1.0, 1e0, -0, very large integer, invalid UTF-8, unpaired surrogate, C0/C1 control, NFC/NFD and nested limits across Python and PostgreSQL.
7. Clean the full SQL file and run it as a complete disposable script, in addition to per-function conformance tests.

## 6. Gate conclusion

G1 remains OPEN. The typed encoding candidate is promising and the current positive-domain byte encoding appears aligned, but the normative ADR is not approved and the maximum-size/argument-binding/Claim parity obligations remain unresolved.

## Change history

- 2026-11-03: Initial canonicalization boundary audit.
