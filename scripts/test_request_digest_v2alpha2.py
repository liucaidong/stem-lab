#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, sys, unittest, jsonschema
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.request_digest_v2alpha2 import RequestEncodingError, canonical_request_bytes, canonical_bytes_base64url, parse_json_strict, request_digest, MAX_REQUEST_JSON_BYTES
VECTOR=json.loads((ROOT/"contracts/examples/worker-request-digest.v2alpha2.golden.json").read_text())
UNICODE_VECTOR=json.loads((ROOT/"contracts/examples/worker-request-digest.v2alpha2.unicode.golden.json").read_text())
SCHEMA=json.loads((ROOT/"contracts/worker-resource-assertion.schema.v2alpha2.json").read_text())
VALID_ASSERTION=json.loads((ROOT/"contracts/examples/worker-resource-assertion.v2alpha2.valid.json").read_text())
INVALID_ASSERTIONS=json.loads((ROOT/"contracts/examples/worker-resource-assertion.v2alpha2.invalid.json").read_text())
class RequestDigestTests(unittest.TestCase):
    def test_schema_itself_is_valid(self):
        jsonschema.Draft202012Validator.check_schema(SCHEMA)
    def test_v2alpha2_schema_valid_and_invalid_examples(self):
        validator=jsonschema.Draft202012Validator(SCHEMA)
        self.assertEqual(list(validator.iter_errors(VALID_ASSERTION)),[])
        for case in INVALID_ASSERTIONS['cases']:
            with self.subTest(case=case['name']): self.assertTrue(list(validator.iter_errors(case['claims'])))
    def test_golden_bytes_base64url_and_sha256(self):
        e=VECTOR["envelope"]
        self.assertEqual(canonical_bytes_base64url(e),VECTOR["canonical_bytes_base64url"])
        self.assertEqual(request_digest(e),VECTOR["request_digest"])
    def test_unicode_golden_vector(self):
        e=UNICODE_VECTOR['envelope']
        self.assertEqual(canonical_bytes_base64url(e),UNICODE_VECTOR['canonical_bytes_base64url'])
        self.assertEqual(request_digest(e),UNICODE_VECTOR['request_digest'])
    def test_object_key_order_is_independent(self):
        e=dict(VECTOR["envelope"]); e["operation_arguments"]={"result_ref":"artifact:abc","expected_session_revision":7}
        self.assertEqual(canonical_request_bytes(e),canonical_request_bytes(VECTOR["envelope"]))
    def test_array_order_is_significant(self):
        from runtime.request_digest_v2alpha2 import _value
        self.assertNotEqual(_value(["a","b"]),_value(["b","a"]))
    def test_unpaired_surrogate_rejected(self):
        from runtime.request_digest_v2alpha2 import _value
        with self.assertRaises(RequestEncodingError): _value('\ud800')
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
    def test_raw_json_size_budget(self):
        with self.assertRaises(RequestEncodingError):
            parse_json_strict(b" " * (MAX_REQUEST_JSON_BYTES + 1))
        with self.assertRaises(RequestEncodingError):
            parse_json_strict(" " * (MAX_REQUEST_JSON_BYTES + 1))
    def test_canonical_request_size_budget(self):
        e=dict(VECTOR["envelope"])
        e["operation_arguments"]={"expected_session_revision":7,"result_ref":"x" * 1025}
        with self.assertRaises(RequestEncodingError):
            canonical_request_bytes(e)
        e["operation_arguments"]={"expected_session_revision":7,"result_ref":"x" * 70000}
        with self.assertRaises(RequestEncodingError):
            canonical_request_bytes(e)
    def test_retry_action_uses_integer_microseconds(self):
        e=dict(VECTOR["envelope"])
        e["action"]="worker.job.retry"
        e["operation_arguments"]={"delay_micros":1000000,"error_code":"DEPENDENCY_UNAVAILABLE"}
        self.assertTrue(request_digest(e).startswith("sha256:"))
        e["operation_arguments"]={"delay_seconds":1,"error_code":"DEPENDENCY_UNAVAILABLE"}
        with self.assertRaises(RequestEncodingError):
            canonical_request_bytes(e)
    def test_fail_action_binds_retry_policy_version_and_safe_message(self):
        e=dict(VECTOR["envelope"])
        e["action"]="worker.job.fail"
        e["operation_arguments"]={"error_code":"DEPENDENCY_UNAVAILABLE","retryable":True,
            "retry_delay_micros":1000000,"retry_policy_version":"2026-11-03.1",
            "safe_message":"Dependency unavailable"}
        self.assertTrue(request_digest(e).startswith("sha256:"))
        e["operation_arguments"].pop("retry_policy_version")
        with self.assertRaises(RequestEncodingError):
            canonical_request_bytes(e)

    def test_dlq_replay_is_not_in_v2alpha2_executable_allowlist(self):
        e=dict(VECTOR["envelope"])
        e["action"]="worker.dlq.replay"
        e["resource_type"]="dlq_item"
        e["resource_id"]="dlq-1"
        e["operation_arguments"]={}
        with self.assertRaises(RequestEncodingError):
            canonical_request_bytes(e)
    def test_version_action_and_resource_binding_rejected(self):
        e=dict(VECTOR["envelope"]); e["contract_version"]="2alpha1"
        with self.assertRaises(RequestEncodingError): canonical_request_bytes(e)
        e=dict(VECTOR["envelope"]); e["action"]="worker.job.unknown"
        with self.assertRaises(RequestEncodingError): canonical_request_bytes(e)
        e=dict(VECTOR["envelope"]); e["resource_id"]="other-job"
        with self.assertRaises(RequestEncodingError): canonical_request_bytes(e)
if __name__=="__main__": unittest.main(verbosity=2)
