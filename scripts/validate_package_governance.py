#!/usr/bin/env python3
"""Structural trust, provenance binding and license-policy checks; no crypto verification."""
from __future__ import annotations
import copy,json,re
from datetime import datetime,timezone
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/"contracts/examples/package-governance.fixtures.v1alpha1.json"
SCHEMAS={
 "attestation":ROOT/"contracts/package-attestation.schema.v1alpha1.json",
 "provenance":ROOT/"contracts/package-provenance.schema.v1alpha1.json",
 "license":ROOT/"contracts/package-license-record.schema.v1alpha1.json"}
class GovernanceError(Exception):
 def __init__(self,code,message): self.code=code; super().__init__(message)
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def parse_time(v): return datetime.fromisoformat(v.replace("Z","+00:00"))
def validate(f):
 subject=f["package_subject"]; att=f["attestation"]; registry={k["key_id"]:k for k in f["trust_registry"]["keys"]}
 if att["package_subject"]!=subject: raise GovernanceError("ATTESTATION_SUBJECT_MISMATCH","attestation does not bind package subject")
 pred=att["predicate"]
 if pred["source"]["revision"]=="" or parse_time(pred["build_finished_at"])<parse_time(pred["build_started_at"]): raise GovernanceError("INVALID_PROVENANCE","invalid build provenance")
 if not pred["materials"]: raise GovernanceError("PROVENANCE_MATERIALS_REQUIRED","materials are required")
 for sig in att["signatures"]:
  key=registry.get(sig["key_id"])
  if key is None: raise GovernanceError("UNKNOWN_SIGNING_KEY",sig["key_id"])
  if key["status"]=="revoked": raise GovernanceError("SIGNING_KEY_REVOKED",sig["key_id"])
  if key["status"]!="active": raise GovernanceError("SIGNING_KEY_NOT_ACTIVE",sig["key_id"])
  if key["signer_identity"]!=sig["signer_identity"]: raise GovernanceError("SIGNER_IDENTITY_MISMATCH",sig["key_id"])
  if key["algorithm"]!=sig["algorithm"]: raise GovernanceError("SIGNATURE_ALGORITHM_MISMATCH",sig["key_id"])
  signed=parse_time(sig["signed_at"])
  if signed<parse_time(key["valid_from"]) or signed>parse_time(key["valid_until"]): raise GovernanceError("SIGNING_KEY_OUTSIDE_VALIDITY",sig["key_id"])
 record=f["license_record"]; policy=f["policy"]
 if record["asset_digest"] not in [m["digest"] for m in pred["materials"]] and record["asset_id"]=="asset:bound-material":
  raise GovernanceError("LICENSE_ASSET_DIGEST_MISMATCH",record["asset_id"])
 review=record["review"]
 if review["status"]!="approved" or not review.get("reviewer_id") or not review.get("approved_at"): raise GovernanceError("LICENSE_REVIEW_REQUIRED",record["asset_id"])
 license_id=record["license_expression"]
 if license_id in policy["denylist"]: raise GovernanceError("LICENSE_DENIED",license_id)
 exception_id=review.get("exception_id")
 if license_id not in policy["allowlist"]:
  if not exception_id: raise GovernanceError("LICENSE_UNKNOWN",license_id)
  ex=next((x for x in policy["exceptions"] if x["exception_id"]==exception_id),None)
  if ex is None or ex["status"]!="approved" or ex["scope_asset_id"]!=record["asset_id"]: raise GovernanceError("LICENSE_EXCEPTION_INVALID",exception_id)
  if parse_time(ex["expires_at"])<datetime(2026,11,2,tzinfo=timezone.utc): raise GovernanceError("LICENSE_EXCEPTION_EXPIRED",exception_id)
 rights=record["rights_assertions"]
 if not rights["commercial_use"] or not rights["redistribution"]: raise GovernanceError("LICENSE_RIGHTS_INSUFFICIENT",license_id)
 return True
def main():
 f=load(FIXTURE)
 for name,path in SCHEMAS.items():
  schema=load(path); jsonschema.Draft202012Validator.check_schema(schema)
  target=f["attestation"] if name=="attestation" else f["attestation"]["predicate"] if name=="provenance" else f["license_record"]
  errors=list(jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker()).iter_errors(target))
  if errors: raise SystemExit(name+" schema: "+errors[0].message)
 validate(f)
 for case in f["invalid_cases"]:
  x=copy.deepcopy(f)
  m=case["mutation"]
  if m=="subject": x["attestation"]["package_subject"]["digest"]="sha256:"+"9"*64
  elif m=="revoked-key": x["attestation"]["signatures"][0]["key_id"]="release-key-2025-retired"
  elif m=="unknown-key": x["attestation"]["signatures"][0]["key_id"]="missing-key"
  elif m=="identity": x["attestation"]["signatures"][0]["signer_identity"]="did:web:attacker.example"
  elif m=="algorithm": x["attestation"]["signatures"][0]["algorithm"]="rsa-pss-sha256"
  elif m=="pending-license": x["license_record"]["review"]["status"]="pending"
  elif m=="denied-license": x["license_record"]["license_expression"]="GPL-3.0-only"
  elif m=="unknown-license": x["license_record"]["license_expression"]="LicenseRef-Unknown"
  elif m=="rights": x["license_record"]["rights_assertions"]["commercial_use"]=False
  elif m=="expired-exception":
   x["license_record"]["asset_id"]="asset:licensed-font"; x["license_record"]["license_expression"]="LicenseRef-Custom"; x["license_record"]["review"]["exception_id"]="EXC-001"
   x["policy"]["exceptions"][0]["expires_at"]="2026-01-01T00:00:00Z"
  elif m=="asset-digest":
   x["license_record"]["asset_id"]="asset:bound-material"; x["license_record"]["asset_digest"]="sha256:"+"c"*64
  try: validate(x); actual="ACCEPTED"
  except GovernanceError as exc: actual=exc.code
  if actual!=case["expected_error"]: raise SystemExit(f'{case["case_id"]}: expected {case["expected_error"]}, got {actual}')
 print(f'PASS: attestation/provenance/license schemas + trust/subject/policy checks + {len(f["invalid_cases"])} negative cases')
 print("LIMIT: signature bytes are NOT cryptographically verified; trust registry and license evidence are synthetic fixtures")
if __name__=="__main__": main()
