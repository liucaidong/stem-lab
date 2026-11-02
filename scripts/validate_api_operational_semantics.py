#!/usr/bin/env python3
"""Static API security and operational semantics tests; JWT signature verification is out of scope."""
from __future__ import annotations
import base64,copy,hashlib,hmac,json
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/"contracts/examples/api-operational-semantics.fixtures.v1alpha1.json"
CMD_SCHEMA=ROOT/"contracts/commands/runtime-command-payloads.schema.v1alpha1.json"
CMD_REG_SCHEMA=ROOT/"contracts/commands/registry.schema.v1alpha1.json"
ERROR_SCHEMA=ROOT/"contracts/api-error-catalog.schema.v1alpha1.json"
ERROR_CATALOG=ROOT/"contracts/api-error-catalog.v1alpha1.json"
class SemanticError(Exception):
 def __init__(self,code): self.code=code; super().__init__(code)
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def validate_jwt_claims(c,now,issuer,audience):
 if c.get("iss")!=issuer: raise SemanticError("JWT_ISSUER_INVALID")
 aud=c.get("aud"); auds=[aud] if isinstance(aud,str) else aud if isinstance(aud,list) else []
 if audience not in auds: raise SemanticError("JWT_AUDIENCE_INVALID")
 if not c.get("sub"): raise SemanticError("JWT_SUBJECT_REQUIRED")
 if not isinstance(c.get("exp"),int) or c["exp"]<=now: raise SemanticError("JWT_EXPIRED")
 if not isinstance(c.get("nbf"),int) or c["nbf"]>now: raise SemanticError("JWT_NOT_YET_VALID")
 if not isinstance(c.get("iat"),int) or c["iat"]>now+60: raise SemanticError("JWT_ISSUED_AT_INVALID")
def authorize(actor_tenant,resource_tenant,roles,required):
 if actor_tenant!=resource_tenant: raise SemanticError("RESOURCE_TENANT_MISMATCH")
 if required not in roles: raise SemanticError("RESOURCE_ROLE_FORBIDDEN")
def idempotency(existing_hash,new_hash):
 if existing_hash is None: return "execute"
 if existing_hash==new_hash: return "replay-original-receipt"
 raise SemanticError("IDEMPOTENCY_KEY_CONFLICT")
def b64(data): return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
def cursor_sign(payload,secret):
 raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
 body=b64(raw); sig=b64(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())
 return "v1."+body+"."+sig
def cursor_verify(token,secret,now,tenant,resource,filter_hash):
 try: version,body,sig=token.split(".")
 except ValueError: raise SemanticError("CURSOR_MALFORMED")
 if version!="v1": raise SemanticError("CURSOR_VERSION_UNSUPPORTED")
 expected=b64(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())
 if not hmac.compare_digest(sig,expected): raise SemanticError("CURSOR_SIGNATURE_INVALID")
 try: payload=json.loads(base64.urlsafe_b64decode(body+"="*((4-len(body)%4)%4)))
 except Exception: raise SemanticError("CURSOR_MALFORMED")
 if payload.get("exp",0)<=now: raise SemanticError("CURSOR_EXPIRED")
 if payload.get("tenant_id")!=tenant: raise SemanticError("CURSOR_TENANT_MISMATCH")
 if payload.get("resource")!=resource or payload.get("filter_hash")!=filter_hash: raise SemanticError("CURSOR_QUERY_MISMATCH")
 return payload
def main():
 f=load(FIXTURE); cmd_schema=load(CMD_SCHEMA); reg_schema=load(CMD_REG_SCHEMA); err_schema=load(ERROR_SCHEMA); catalog=load(ERROR_CATALOG)
 for s in (cmd_schema,reg_schema,err_schema): jsonschema.Draft202012Validator.check_schema(s)
 for s,obj in ((reg_schema,f["command_registry"]),(err_schema,catalog)):
  es=list(jsonschema.Draft202012Validator(s).iter_errors(obj))
  if es: raise SystemExit("schema failure: "+es[0].message)
 payload_defs=cmd_schema["$defs"]
 seen=set()
 for cmd in f["command_registry"]["commands"]:
  key=(cmd["command_type"],cmd["schema_version"])
  if key in seen: raise SystemExit("duplicate command registry key "+str(key))
  seen.add(key)
  ref=cmd["payload_schema_ref"].split("/")[-1]
  if ref not in payload_defs: raise SystemExit("unknown command payload schema "+ref)
  payload=f["valid_payloads"][cmd["command_type"]]
  es=list(jsonschema.Draft202012Validator(payload_defs[ref]).iter_errors(payload))
  if es: raise SystemExit(cmd["command_type"]+": "+es[0].message)
 codes=[e["code"] for e in catalog["errors"]]
 if len(codes)!=len(set(codes)): raise SystemExit("duplicate API error code")
 for case in f["security_cases"]["jwt"]["invalid"]:
  try: validate_jwt_claims(case["claims"],f["security_cases"]["jwt"]["now"],f["security_cases"]["jwt"]["issuer"],f["security_cases"]["jwt"]["audience"]); actual="ACCEPTED"
  except SemanticError as e: actual=e.code
  if actual!=case["error"]: raise SystemExit(case["case_id"]+": expected "+case["error"]+", got "+actual)
 auth=f["security_cases"]["authorization"]
 try: authorize(**{k:auth["valid"][k] for k in ("tenant_id","resource_tenant_id","actor_roles","required_role")})
 except SemanticError as e: raise SystemExit("valid authorization rejected "+e.code)
 for case in auth["invalid"]:
  try: authorize(case["tenant_id"],case["resource_tenant_id"],case["actor_roles"],case["required_role"]); actual="ACCEPTED"
  except SemanticError as e: actual=e.code
  if actual!=case["error"]: raise SystemExit(case["case_id"]+": expected "+case["error"]+", got "+actual)
 idem=f["security_cases"]["idempotency"]
 if idempotency("hash-1","hash-1")!=idem["same_key_same_hash"]: raise SystemExit("idempotency replay semantics mismatch")
 try: idempotency("hash-1","hash-2"); actual="ACCEPTED"
 except SemanticError as e: actual=e.code
 if actual!="IDEMPOTENCY_KEY_CONFLICT": raise SystemExit("idempotency conflict not detected")
 cur=f["security_cases"]["cursor"]; token=cursor_sign(cur["valid_payload"],cur["secret"])
 cursor_verify(token,cur["secret"],cur["now"],"tenant-a","observations","f123")
 for payload,expected in (({**cur["valid_payload"],"exp":cur["now"]},"CURSOR_EXPIRED"),({**cur["valid_payload"],"tenant_id":"tenant-b"},"CURSOR_TENANT_MISMATCH"),({**cur["valid_payload"],"filter_hash":"different"},"CURSOR_QUERY_MISMATCH")):
  bad=cursor_sign(payload,cur["secret"])
  try: cursor_verify(bad,cur["secret"],cur["now"],"tenant-a","observations","f123"); actual="ACCEPTED"
  except SemanticError as e: actual=e.code
  if actual!=expected: raise SystemExit("cursor expected "+expected+", got "+actual)
 parts=token.split("."); tampered=parts[0]+"."+parts[1]+"."+("A" if parts[2][0]!="A" else "B")+parts[2][1:]
 try: cursor_verify(tampered,cur["secret"],cur["now"],"tenant-a","observations","f123"); actual="ACCEPTED"
 except SemanticError as e: actual=e.code
 if actual!="CURSOR_SIGNATURE_INVALID": raise SystemExit("cursor tampering not detected")
 print(f'PASS: API Error Catalog + {len(seen)} command payload mappings + JWT claims/resource authorization/idempotency/cursor HMAC semantics')
 print("LIMIT: JWT signature/JWKS validation, distributed rate limiting and real API middleware are NOT tested")
if __name__=="__main__": main()
