"""Experimental v2alpha2 typed request encoding; proposal/reference only."""
from __future__ import annotations
import base64, hashlib, json, re, struct
from typing import Any

DOMAIN = b"STEMLAB-REQUEST-DIGEST\x00v2alpha2\x00"
MAX_REQUEST_JSON_BYTES = 65536
MAX_CANONICAL_REQUEST_BYTES = 65536
ENVELOPE_FIELDS = ("contract_version","action","tenant_id","job_id","session_id","resource_type","resource_id","operation_id","idempotency_key")
ACTIONS = {
 "worker.job.renew": ("lease_seconds",),
 "worker.job.complete": ("expected_session_revision","result_ref"),
 "worker.job.fail": ("error_code","retryable","retry_delay_micros","retry_policy_version","safe_message"),
 "worker.job.retry": ("delay_micros","error_code"),
 "worker.job.dead_letter": ("error_code","terminal_reason"),
 "worker.outbox.dispatch": ("lease_seconds",),
 "worker.receipt.reconcile": (),
 "worker.outbox.ack": (),
}
RESOURCE_FOR_ACTION = {
 "worker.job.renew":"job","worker.job.complete":"job","worker.job.fail":"job",
 "worker.job.retry":"job","worker.job.dead_letter":"job",
"worker.outbox.dispatch":"outbox_event",
 "worker.receipt.reconcile":"receipt","worker.outbox.ack":"outbox_event",
}
ID_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")

class RequestEncodingError(ValueError): pass

def _u32(n: int) -> bytes:
    if not 0 <= n <= 0x7fffffff: raise RequestEncodingError("length/count out of range")
    return struct.pack(">I", n)

def _lp(raw: bytes) -> bytes: return _u32(len(raw)) + raw

def _utf8(value: str) -> bytes:
    if not isinstance(value,str): raise RequestEncodingError("expected string")
    try: return value.encode("utf-8",errors="strict")
    except UnicodeEncodeError as exc: raise RequestEncodingError("unpaired surrogate forbidden") from exc

def _value(value: Any, depth: int=0) -> bytes:
    if depth > 32: raise RequestEncodingError("maximum nesting depth exceeded")
    if value is None: return b"N"
    if value is False: return b"F"
    if value is True: return b"T"
    if isinstance(value,int):
        if not -(2**63) <= value <= 2**63-1: raise RequestEncodingError("integer outside signed int64")
        return b"I" + _lp(str(value).encode("ascii"))
    if isinstance(value,float): raise RequestEncodingError("floating point forbidden")
    if isinstance(value,str): return b"S" + _lp(_utf8(value))
    if isinstance(value,list):
        if len(value)>4096: raise RequestEncodingError("array too large")
        return b"A" + _u32(len(value)) + b"".join(_value(v,depth+1) for v in value)
    if isinstance(value,dict):
        if len(value)>4096: raise RequestEncodingError("object too large")
        pairs=sorted(((_utf8(k),v) for k,v in value.items()),key=lambda p:p[0])
        return b"O" + _u32(len(pairs)) + b"".join(_lp(k)+_value(v,depth+1) for k,v in pairs)
    raise RequestEncodingError("unsupported value type")

def parse_json_strict(raw: bytes|str) -> Any:
    try:
        if isinstance(raw, bytes):
            if len(raw) > MAX_REQUEST_JSON_BYTES:
                raise RequestEncodingError("request JSON exceeds 65536-byte limit")
            source=raw.decode("utf-8",errors="strict")
        elif isinstance(raw, str):
            if len(_utf8(raw)) > MAX_REQUEST_JSON_BYTES:
                raise RequestEncodingError("request JSON exceeds 65536-byte limit")
            source=raw
        else:
            raise RequestEncodingError("request JSON must be bytes or string")
        def pairs_hook(pairs):
            result={}
            for key,value in pairs:
                if key in result: raise RequestEncodingError("duplicate JSON key: "+key)
                result[key]=value
            return result
        def reject_constant(value): raise RequestEncodingError("invalid numeric constant: "+value)
        return json.loads(source,object_pairs_hook=pairs_hook,parse_constant=reject_constant)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise RequestEncodingError("invalid UTF-8 JSON") from exc

def validate_envelope(e: dict[str,Any]) -> None:
    if not isinstance(e,dict): raise RequestEncodingError("envelope must be object")
    if set(e) != set(ENVELOPE_FIELDS)|{"operation_arguments"}: raise RequestEncodingError("missing or unknown envelope fields")
    if e["contract_version"]!="2alpha2": raise RequestEncodingError("unsupported contract version")
    if e["action"] not in ACTIONS: raise RequestEncodingError("unsupported action")
    for field in ENVELOPE_FIELDS:
        if not isinstance(e[field],str) or not ID_RE.fullmatch(e[field]): raise RequestEncodingError("invalid "+field)
    if e["resource_type"] != RESOURCE_FOR_ACTION[e["action"]]: raise RequestEncodingError("action/resource_type mismatch")
    if e["action"].startswith("worker.job.") and e["resource_id"] != e["job_id"]:
        raise RequestEncodingError("Job action resource_id must equal job_id")
    if e["action"]=="worker.receipt.reconcile" and e["resource_id"] != e["operation_id"]:
        raise RequestEncodingError("Receipt resource_id must equal operation_id")
    args=e["operation_arguments"]
    if not isinstance(args,dict) or set(args)!=set(ACTIONS[e["action"]]): raise RequestEncodingError("operation arguments do not match action")
    for key,value in args.items():
        if key in {"lease_seconds","delay_micros","expected_session_revision","retry_delay_micros"}:
            if type(value) is not int or value<0 or value>2**63-1: raise RequestEncodingError(key+" must be non-negative int64")
        elif key=="retryable":
            if type(value) is not bool: raise RequestEncodingError("retryable must be boolean")
        elif not isinstance(value,str): raise RequestEncodingError(key+" must be string")
    if e["action"]=="worker.job.renew" and not 5<=args["lease_seconds"]<=300: raise RequestEncodingError("job lease_seconds out of range")
    if e["action"]=="worker.outbox.dispatch" and not 5<=args["lease_seconds"]<=3600: raise RequestEncodingError("outbox lease_seconds out of range")
    if e["action"]=="worker.job.retry" and not 1<=args["delay_micros"]<=86400000000: raise RequestEncodingError("delay_micros out of range")
    if "retry_delay_micros" in args and args["retry_delay_micros"] > 86400000000:
        raise RequestEncodingError("retry_delay_micros out of range")
    if e["action"]=="worker.job.fail" and not args["retryable"] and args["retry_delay_micros"] != 0:
        raise RequestEncodingError("non-retryable failure must have zero delay")
    if e["action"]=="worker.job.complete":
        if not 0<=args["expected_session_revision"]<=2147483646: raise RequestEncodingError("expected_session_revision out of int32 range")
        if not 1<=len(args["result_ref"])<=1024: raise RequestEncodingError("result_ref must contain 1..1024 characters")
    if e["action"]=="worker.job.fail":
        if not 1<=len(args["safe_message"])<=512: raise RequestEncodingError("safe_message must contain 1..512 characters")
        if not 1<=len(args["retry_policy_version"])<=128: raise RequestEncodingError("retry_policy_version must contain 1..128 characters")
    if e["action"] in {"worker.job.fail","worker.job.retry","worker.job.dead_letter"} and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}",args["error_code"]): raise RequestEncodingError("invalid error_code")
    if e["action"]=="worker.job.dead_letter" and args["terminal_reason"] not in {"max_attempts","non_retryable"}: raise RequestEncodingError("invalid terminal_reason")

def canonical_request_bytes(e: dict[str,Any]) -> bytes:
    validate_envelope(e)
    out=bytearray(DOMAIN)
    for field in ENVELOPE_FIELDS: out.extend(b"S"+_lp(_utf8(e[field])))
    encoded_args=_value(e["operation_arguments"])
    out.extend(b"J"+_lp(encoded_args))
    if len(out) > MAX_CANONICAL_REQUEST_BYTES:
        raise RequestEncodingError("canonical request exceeds 65536-byte limit")
    return bytes(out)

def canonical_request_bytes_from_json(raw: bytes|str) -> bytes:
    value=parse_json_strict(raw)
    if not isinstance(value,dict): raise RequestEncodingError("Request Envelope must be a JSON object")
    return canonical_request_bytes(value)

def request_digest(e: dict[str,Any]) -> str:
    return "sha256:"+hashlib.sha256(canonical_request_bytes(e)).hexdigest()

def canonical_bytes_base64url(e: dict[str,Any]) -> str:
    return base64.urlsafe_b64encode(canonical_request_bytes(e)).rstrip(b"=").decode("ascii")
