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
        for statement in SQL.split("\n\n"):
            if statement.strip(): conn.execute(statement)
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
        print("PostgreSQL object-key order invariance: PASS")
        print("PostgreSQL invalid-argument rejection: PASS")
    finally:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.close()
if __name__=="__main__": main()
