#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.request_digest_v2alpha2 import RequestEncodingError, canonical_request_bytes, canonical_bytes_base64url, parse_json_strict, request_digest
VECTOR=json.loads((ROOT/"contracts/examples/worker-request-digest.v2alpha2.golden.json").read_text())
class RequestDigestTests(unittest.TestCase):
    def test_golden_bytes_base64url_and_sha256(self):
        e=VECTOR["envelope"]
        self.assertEqual(canonical_bytes_base64url(e),VECTOR["canonical_bytes_base64url"])
        self.assertEqual(request_digest(e),VECTOR["request_digest"])
    def test_object_key_order_is_independent(self):
        e=dict(VECTOR["envelope"]); e["operation_arguments"]={"result_ref":"artifact:abc","expected_session_revision":7}
        self.assertEqual(canonical_request_bytes(e),canonical_request_bytes(VECTOR["envelope"]))
    def test_array_order_is_significant(self):
        from runtime.request_digest_v2alpha2 import _value
        self.assertNotEqual(_value(["a","b"]),_value(["b","a"]))
    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(RequestEncodingError): parse_json_strict('{"a":1,"a":2}')
    def test_float_and_nonfinite_rejected(self):
        from runtime.request_digest_v2alpha2 import _value
        for value in (1.0,float("nan"),float("inf")):
            with self.assertRaises(RequestEncodingError): _value(value)
    def test_unknown_or_missing_fields_rejected(self):
        e=dict(VECTOR["envelope"]); e["unexpected"]="x"
        with self.assertRaises(RequestEncodingError): canonical_request_bytes(e)
    def test_absent_and_null_are_distinct(self):
        from runtime.request_digest_v2alpha2 import _value
        self.assertNotEqual(_value({}),_value({"x":None}))
    def test_unicode_is_exact_utf8_not_normalized(self):
        from runtime.request_digest_v2alpha2 import _value
        self.assertNotEqual(_value("é"),_value("e\u0301"))
    def test_int64_boundaries(self):
        from runtime.request_digest_v2alpha2 import _value
        _value(2**63-1); _value(-(2**63))
        with self.assertRaises(RequestEncodingError): _value(2**63)
    def test_version_action_and_resource_binding_rejected(self):
        e=dict(VECTOR["envelope"]); e["contract_version"]="2alpha1"
        with self.assertRaises(RequestEncodingError): canonical_request_bytes(e)
        e=dict(VECTOR["envelope"]); e["action"]="worker.job.unknown"
        with self.assertRaises(RequestEncodingError): canonical_request_bytes(e)
        e=dict(VECTOR["envelope"]); e["resource_id"]="other-job"
        with self.assertRaises(RequestEncodingError): canonical_request_bytes(e)
if __name__=="__main__": unittest.main(verbosity=2)
