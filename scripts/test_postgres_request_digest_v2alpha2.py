#!/usr/bin/env python3
from __future__ import annotations
import base64, json, os, pathlib, time, uuid
import psycopg
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.request_digest_v2alpha2 import request_digest
DSN=os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/stemlab_test")
SCHEMA="request_digest_"+uuid.uuid4().hex[:12]
VECTOR=json.loads((ROOT/"contracts/examples/worker-request-digest.v2alpha2.golden.json").read_text())
SQL=(ROOT/"sql/request-digest-v2alpha2.sql").read_text().replace("__SCHEMA__",SCHEMA)

def main() -> None:
    conn=psycopg.connect(DSN,autocommit=True)
    try:
        encoding=conn.execute('SHOW server_encoding').fetchone()[0]
        assert encoding.upper()=='UTF8', f'PostgreSQL database encoding must be UTF8, got {encoding}'
        conn.execute("CREATE SCHEMA " + SCHEMA)
        conn.execute("CREATE EXTENSION IF NOT EXISTS pgsodium")
        conn.execute("LOAD 'pgsodium'")
        public_key, private_key = conn.execute("SELECT public,secret FROM pgsodium.crypto_sign_new_keypair()").fetchone()
        conn.execute(f"CREATE TABLE {SCHEMA}.issuer_keys (kid text PRIMARY KEY, issuer text NOT NULL, public_key bytea NOT NULL, not_before timestamptz NOT NULL, not_after timestamptz, revoked_at timestamptz)")
        conn.execute(f"INSERT INTO {SCHEMA}.issuer_keys(kid,issuer,public_key,not_before) VALUES ('test-key','test-issuer',%s,clock_timestamp()-interval '1 day')",(public_key,))
        # Execute the complete SQL asset as shipped; splitting functions masked malformed trailing fragments.
        conn.execute(SQL, prepare=False)
        strict_parser=f"SELECT {SCHEMA}.parse_strict_json_object_v2alpha2(%s)"
        valid_raw='{"outer":[{"x":1,"y":2}]}'
        parsed=conn.execute(strict_parser,(valid_raw,)).fetchone()[0]
        assert parsed=={"outer":[{"x":1,"y":2}]}, "strict raw JSON parser changed valid object"
        for duplicate_raw in (
            '{"action":"worker.job.complete","action":"worker.job.fail"}',
            '{"outer":{"claim":"a","claim":"b"}}',
            '{"items":[{"nonce":"n1","nonce":"n2"}]}',
        ):
            try:
                conn.execute(strict_parser,(duplicate_raw,))
            except psycopg.Error:
                pass
            else:
                raise AssertionError(f"PostgreSQL accepted duplicate JSON object key: {duplicate_raw}")
        print("PostgreSQL strict raw-claim JSON duplicate-key rejection: PASS")
        envelope=VECTOR["envelope"]
        claim=dict(envelope)
        claim.pop("operation_arguments")
        claim.update({"v":2,"iss":"test-issuer","kid":"test-key","sub":"worker-a",
            "aud":"stemlab-worker-store","owner":"worker-a","epoch":7,
            "request_digest":VECTOR["request_digest"],"iat":1800000000,"exp":1800000060,
            "nonce":"0123456789abcdef0123456789abcdef"})
        args=envelope["operation_arguments"]
        call=f"SELECT {SCHEMA}.assert_request_digest_v2alpha2(%s::jsonb,%s::jsonb)"
        result=conn.execute(call,(json.dumps(claim,ensure_ascii=False),json.dumps(args,ensure_ascii=False))).fetchone()[0]
        assert result is True, "PostgreSQL digest differs from Python golden vector"
        mismatched_envelope=dict(envelope)
        mismatched_envelope["resource_type"]="receipt"
        try:
            conn.execute(f"SELECT {SCHEMA}.request_digest_v2alpha2(%s::jsonb)", (json.dumps(mismatched_envelope,ensure_ascii=False),))
        except psycopg.Error as exc:
            assert "action/resource type mismatch" in str(exc), f"unexpected mismatch error: {exc}"
        else:
            raise AssertionError("PostgreSQL accepted an action/resource type mismatch")
        print("PostgreSQL action/resource mismatch rejection: PASS")
        mapping_cases = (
            ("worker.job.renew", "job", "job-1", {"lease_seconds": 30}),
            ("worker.job.complete", "job", "job-1", {"expected_session_revision": 7, "result_ref": "artifact:abc"}),
            ("worker.job.fail", "job", "job-1", {"error_code": "WORKER_FAILED", "retryable": True, "retry_delay_micros": 1000, "retry_policy_version": "2026-11-03.1", "safe_message": "failed safely"}),
            ("worker.job.retry", "job", "job-1", {"delay_micros": 1000000, "error_code": "WORKER_FAILED"}),
            ("worker.job.dead_letter", "job", "job-1", {"error_code": "WORKER_FAILED", "terminal_reason": "max_attempts"}),
            ("worker.outbox.dispatch", "outbox_event", "event-1", {"lease_seconds": 30}),
            ("worker.outbox.ack", "outbox_event", "event-1", {}),
            ("worker.receipt.reconcile", "receipt", "op-01", {}),
        )
        for action, resource_type, resource_id, operation_arguments in mapping_cases:
            mapped = dict(envelope)
            mapped.update({"action": action, "resource_type": resource_type, "resource_id": resource_id, "operation_arguments": operation_arguments})
            conn.execute(f"SELECT {SCHEMA}.request_digest_v2alpha2(%s::jsonb)", (json.dumps(mapped,ensure_ascii=False),))
        print("PostgreSQL action/resource mapping matrix (8 supported actions): PASS")
        unicode_vector=json.loads((ROOT/"contracts/examples/worker-request-digest.v2alpha2.unicode.golden.json").read_text())
        unicode_envelope=unicode_vector["envelope"]
        unicode_claim=dict(unicode_envelope); unicode_claim.pop("operation_arguments")
        unicode_claim.update({"v":2,"iss":"test-issuer","kid":"test-key","sub":"worker-a",
            "aud":"stemlab-worker-store","owner":"worker-a","epoch":7,
            "request_digest":unicode_vector["request_digest"],"iat":1800000000,"exp":1800000060,
            "nonce":"abcdef0123456789abcdef0123456789"})
        unicode_result=conn.execute(call,(json.dumps(unicode_claim,ensure_ascii=False),json.dumps(unicode_envelope["operation_arguments"],ensure_ascii=False))).fetchone()[0]
        assert unicode_result is True, "PostgreSQL Unicode golden vector differs from Python"
        changed=dict(args); changed["result_ref"]="artifact:tampered"
        result=conn.execute(call,(json.dumps(claim,ensure_ascii=False),json.dumps(changed,ensure_ascii=False))).fetchone()[0]
        assert result is False, "PostgreSQL accepted tampered business argument"
        reordered={"result_ref":"artifact:abc","expected_session_revision":7}
        result=conn.execute(call,(json.dumps(claim,ensure_ascii=False),json.dumps(reordered,ensure_ascii=False))).fetchone()[0]
        assert result is True, "PostgreSQL object key order changed the digest"
        for bad_args in (
            {"expected_session_revision":7.0,"result_ref":"artifact:abc"},
            {"expected_session_revision":7,"result_ref":"artifact:abc","unknown":"x"},
            {"expected_session_revision":7,"result_ref":""},
            {"expected_session_revision":7,"result_ref":"x"*1025},
        ):
            try: conn.execute(call,(json.dumps(claim,ensure_ascii=False),json.dumps(bad_args,ensure_ascii=False)))
            except psycopg.Error: pass
            else: raise AssertionError(f"PostgreSQL accepted invalid arguments: {bad_args!r}")
        oversized=dict(envelope)
        oversized["operation_arguments"]={"expected_session_revision":7,"result_ref":"x"*70000}
        try: conn.execute(f"SELECT {SCHEMA}.request_digest_v2alpha2(%s::jsonb)",(json.dumps(oversized),))
        except psycopg.Error: pass
        else: raise AssertionError("PostgreSQL accepted oversized request envelope")
        print("PostgreSQL Request Digest v2alpha2 golden vector: PASS")
        print("PostgreSQL full SQL asset execution and 64 KiB request budget: PASS")
        print("PostgreSQL tampered-argument rejection: PASS")
        print("PostgreSQL Unicode golden vector: PASS")
        print("PostgreSQL object-key order invariance: PASS")
        fail_envelope=dict(envelope)
        fail_envelope["action"]="worker.job.fail"
        fail_envelope["operation_arguments"]={
            "error_code":"DEPENDENCY_UNAVAILABLE","retryable":True,
            "retry_delay_micros":1000000,"retry_policy_version":"2026-11-03.1",
            "safe_message":"Dependency unavailable"
        }
        fail_digest=request_digest(fail_envelope)
        fail_claim=dict(claim)
        fail_claim.update({"action":"worker.job.fail","request_digest":fail_digest})
        fail_args=fail_envelope["operation_arguments"]
        assert conn.execute(call,(json.dumps(fail_claim),json.dumps(fail_args))).fetchone()[0] is True
        missing_policy_version=dict(fail_args)
        missing_policy_version.pop("retry_policy_version")
        try: conn.execute(call,(json.dumps(fail_claim),json.dumps(missing_policy_version)))
        except psycopg.Error: pass
        else: raise AssertionError("PostgreSQL accepted fail action without retry_policy_version")
        print("PostgreSQL fail action policy-version binding and validation: PASS")
        print("PostgreSQL invalid-argument rejection: PASS")

        # Sign and verify the exact decoded raw payload bytes.
        verify_claim=dict(claim)
        verify_claim.update({"v":2,"iss":"test-issuer","kid":"test-key","sub":"worker-a",
            "aud":"stemlab-worker-store","owner":"worker-a","epoch":7,
            "iat":int(time.time()),"exp":int(time.time())+60,
            "nonce":"0123456789abcdef0123456789abcdef"})
        raw_payload=json.dumps(verify_claim,ensure_ascii=False,separators=(",",":")).encode("utf-8")
        payload_b64=base64.urlsafe_b64encode(raw_payload).rstrip(b"=").decode("ascii")
        signature=conn.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(raw_payload,private_key)).fetchone()[0]
        signature_b64=base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        verify_sql=f"SELECT {SCHEMA}.verify_request_assertion_v2alpha2(%s,%s,%s::jsonb)"
        # A 64-byte signature has 2 unused low bits in its final Base64URL symbol.
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        last_index=alphabet.index(signature_b64[-1])
        noncanonical_signature=signature_b64[:-1]+alphabet[last_index | 1]
        try: conn.execute(verify_sql,(payload_b64,noncanonical_signature,json.dumps(args)))
        except psycopg.Error: pass
        else: raise AssertionError("PostgreSQL accepted non-canonical Base64URL pad bits")
        print("PostgreSQL non-canonical Base64URL rejection: PASS")
        verified=conn.execute(verify_sql,(payload_b64,signature_b64,json.dumps(args))).fetchone()[0]
        assert verified["contract_version"]=="2alpha2"
        print("PostgreSQL v2alpha2 raw-payload Ed25519 verification and digest binding: PASS")

        bad_signature=conn.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(raw_payload+b" ",private_key)).fetchone()[0]
        bad_signature_b64=base64.urlsafe_b64encode(bad_signature).rstrip(b"=").decode("ascii")
        try: conn.execute(verify_sql,(payload_b64,bad_signature_b64,json.dumps(args)))
        except psycopg.Error: pass
        else: raise AssertionError("PostgreSQL accepted an invalid Ed25519 signature")

        duplicate_raw=raw_payload.decode("utf-8").replace('"action":"worker.job.complete"','"action":"worker.job.complete","action":"worker.job.fail"',1).encode("utf-8")
        duplicate_payload=base64.urlsafe_b64encode(duplicate_raw).rstrip(b"=").decode("ascii")
        duplicate_signature=conn.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(duplicate_raw,private_key)).fetchone()[0]
        duplicate_signature_b64=base64.urlsafe_b64encode(duplicate_signature).rstrip(b"=").decode("ascii")
        try: conn.execute(verify_sql,(duplicate_payload,duplicate_signature_b64,json.dumps(args)))
        except psycopg.Error: pass
        else: raise AssertionError("PostgreSQL accepted a signed duplicate-key Claim")

        try: conn.execute(verify_sql,(payload_b64,signature_b64,json.dumps(changed)))
        except psycopg.Error: pass
        else: raise AssertionError("PostgreSQL accepted an operation-argument digest mismatch")
        print("PostgreSQL v2alpha2 invalid-signature, duplicate-key and digest-mismatch rejection: PASS")
    finally:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.close()
if __name__=="__main__": main()
