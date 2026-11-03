#!/usr/bin/env python3
from __future__ import annotations
import json, os, pathlib, uuid
import psycopg
ROOT=pathlib.Path(__file__).resolve().parents[1]
DSN=os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/stemlab_test")
SCHEMA="request_digest_"+uuid.uuid4().hex[:12]
VECTOR=json.loads((ROOT/"contracts/examples/worker-request-digest.v2alpha2.golden.json").read_text())
SQL=(ROOT/"sql/request-digest-v2alpha2.sql").read_text().replace("__SCHEMA__",SCHEMA)

def main() -> None:
    conn=psycopg.connect(DSN,autocommit=True)
    try:
        encoding=conn.execute('SHOW server_encoding').fetchone()[0]
        assert encoding.upper()=='UTF8', f'PostgreSQL database encoding must be UTF8, got {encoding}'
        parts=SQL.split("CREATE OR REPLACE FUNCTION ")
        assert len(parts)==6, f"expected schema + 5 function definitions, got {len(parts)}"
        conn.execute(parts[0].strip())
        for function_source in parts[1:]:
            body=function_source.split("$fn$;",1)[0]
            conn.execute("CREATE OR REPLACE FUNCTION "+body+"$fn$;")
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
        ):
            try: conn.execute(call,(json.dumps(claim,ensure_ascii=False),json.dumps(bad_args,ensure_ascii=False)))
            except psycopg.Error: pass
            else: raise AssertionError(f"PostgreSQL accepted invalid arguments: {bad_args!r}")
        print("PostgreSQL Request Digest v2alpha2 golden vector: PASS")
        print("PostgreSQL tampered-argument rejection: PASS")
        print("PostgreSQL Unicode golden vector: PASS")
        print("PostgreSQL object-key order invariance: PASS")
        print("PostgreSQL invalid-argument rejection: PASS")
    finally:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.close()
if __name__=="__main__": main()
