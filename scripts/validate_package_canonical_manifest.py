#!/usr/bin/env python3
"""Candidate canonicalization comparison; does not select a production profile."""
from __future__ import annotations
import copy,hashlib,json,math,unicodedata,runpy
from pathlib import Path
import cbor2,jsonschema,rfc8785
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/"contracts/package-canonical-manifest.schema.v1alpha1.json"
FIXTURE=ROOT/"contracts/examples/package-canonical-manifest.fixtures.v1alpha1.json"
class CanonicalError(Exception):
 def __init__(self,code,message): self.code=code; super().__init__(message)
def load(path):
 def pairs(items):
  out={}
  for k,v in items:
   if k in out: raise ValueError("duplicate JSON property: "+k)
   out[k]=v
  return out
 def reject(v): raise ValueError("non-JSON numeric constant: "+v)
 return json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=pairs,parse_constant=reject)
def validate_json_values(value):
 if isinstance(value,float) and not math.isfinite(value): raise CanonicalError("NON_FINITE_NUMBER","non-finite JSON number")
 if isinstance(value,dict):
  for k,v in value.items():
   if not isinstance(k,str): raise CanonicalError("INVALID_OBJECT_KEY","object keys must be strings")
   validate_json_values(v)
 elif isinstance(value,list):
  for v in value: validate_json_values(v)
def normalize_path(path):
 if not isinstance(path,str) or not path or path.startswith("/") or "\\" in path or any(x in ("",".","..") for x in path.split("/")):
  raise CanonicalError("UNSAFE_RESOURCE_PATH",str(path))
 if unicodedata.normalize("NFC",path)!=path: raise CanonicalError("NON_CANONICAL_UNICODE_PATH",path)
 return path
def normalize_projection(projection):
 out=copy.deepcopy(projection); validate_json_values(out)
 seen=set(); folded=set()
 for resource in out["resources"]:
  path=normalize_path(resource["path"])
  if path in seen: raise CanonicalError("DUPLICATE_RESOURCE_PATH",path)
  if path.casefold() in folded: raise CanonicalError("RESOURCE_PATH_CASE_COLLISION",path)
  seen.add(path); folded.add(path.casefold())
 out["resources"].sort(key=lambda x:x["path"].encode("utf-8"))
 dep_keys=[(x["resource_type"],x["resource_id"],x["version"],x["digest"]) for x in out["dependency_closure"]]
 if len(dep_keys)!=len(set(dep_keys)): raise CanonicalError("DUPLICATE_DEPENDENCY","duplicate dependency identity")
 out["dependency_closure"].sort(key=lambda x:(x["resource_type"].encode(),x["resource_id"].encode(),x["version"].encode(),x["digest"].encode()))
 return out
def candidate_bytes(profile,payload):
 if profile=="rfc8785-jcs": return rfc8785.dumps(payload)
 if profile=="cbor-rfc8949-core": return cbor2.dumps(payload,canonical=True)
 raise ValueError(profile)
def digest(profile,data):
 return "sha256:"+hashlib.sha256(b"stemlab-package-digest\x00"+profile.encode("ascii")+b"\x00"+data).hexdigest()
def main():
 schema,fixture=load(SCHEMA),load(FIXTURE)
 jsonschema.Draft202012Validator.check_schema(schema)
 errors=list(jsonschema.Draft202012Validator(schema).iter_errors(fixture["projection"]))
 if errors: raise SystemExit("projection schema invalid: "+errors[0].message)
 base=normalize_projection(fixture["projection"])
 reversed_input=copy.deepcopy(fixture["projection"])
 reversed_input["resources"].reverse(); reversed_input["dependency_closure"].reverse()
 perturbed=normalize_projection(reversed_input)
 if base!=perturbed: raise SystemExit("normalization is not order invariant")
 for profile in ("rfc8785-jcs","cbor-rfc8949-core"):
  first=candidate_bytes(profile,base); second=candidate_bytes(profile,perturbed)
  if first!=second: raise SystemExit(profile+": canonical bytes differ after ordering perturbation")
  if digest(profile,first)!=digest(profile,second): raise SystemExit(profile+": digest differs after ordering perturbation")
  changed=copy.deepcopy(base); changed["resources"][0]["digest"]="sha256:"+"9"*64
  if digest(profile,candidate_bytes(profile,changed))==digest(profile,first): raise SystemExit(profile+": resource change did not change digest")
 for case in fixture["invalid_cases"]:
  mutated=copy.deepcopy(base)
  if case["mutation"]=="path-traversal": mutated["resources"][0]["path"]="../escape"
  elif case["mutation"]=="duplicate-path": mutated["resources"].append(copy.deepcopy(mutated["resources"][0]))
  elif case["mutation"]=="case-collision": mutated["resources"][1]["path"]=mutated["resources"][0]["path"].upper()
  elif case["mutation"]=="non-nfc-path": mutated["resources"][0]["path"]="assets/cafe\u0301.svg"
  elif case["mutation"]=="non-finite-number": mutated["content"]["bad_number"]=float("inf")
  try: normalize_projection(mutated); actual="ACCEPTED"
  except CanonicalError as exc: actual=exc.code
  if actual!=case["expected_error"]: raise SystemExit(f'{case["case_id"]}: expected {case["expected_error"]}, got {actual}')
 print("PASS: canonical projection schema + resource/dependency ordering + JCS/CBOR deterministic candidate repeatability + digest sensitivity + 5 negative cases")
 print("CANDIDATES ONLY: RFC 8785 JCS and RFC 8949 core deterministic CBOR both exercised; DEC-27 remains OPEN")
 runpy.run_path(str(ROOT/"scripts/validate_package_canonicalization_golden_vectors.py"),run_name="__main__")
if __name__=="__main__": main()
