#!/usr/bin/env python3
"""Registry-driven event metadata and compatibility policy checks."""
from __future__ import annotations
import copy,json,re
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/"contracts/events/registry.schema.v1alpha1.json"
REGISTRY=ROOT/"contracts/events/registry.v1.json"
FIXTURE=ROOT/"contracts/examples/event-registry.validation.fixtures.v1alpha1.json"
class RegistryError(Exception):
 def __init__(self,code,msg): self.code=code; super().__init__(msg)
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def validate(reg):
 keys=set()
 for e in reg["events"]:
  key=(e["event_type"],e["schema_version"])
  if key in keys: raise RegistryError("DUPLICATE_EVENT_VERSION",str(key))
  keys.add(key)
  if not e["producer_ids"]: raise RegistryError("PRODUCER_REQUIRED",e["event_type"])
  if not 1<=e["retention_days"]<=36500: raise RegistryError("INVALID_RETENTION",e["event_type"])
  major,minor=map(int,e["schema_version"].split("."))
  comp=e["compatibility"]; change=comp["change_class"]
  for old in comp["compatible_with"]:
   om,on=map(int,old.split("."))
   if change=="additive" and (major!=om or minor<=on): raise RegistryError("INCOMPATIBLE_VERSION_DECLARATION",e["event_type"])
   if change=="breaking" and major<=om: raise RegistryError("INCOMPATIBLE_VERSION_DECLARATION",e["event_type"])
  if e["lifecycle"]=="active" and any(x in e for x in ("deprecated_at","sunset_at")): raise RegistryError("INVALID_LIFECYCLE_METADATA",e["event_type"])
  if e["lifecycle"]=="deprecated":
   if "deprecated_at" not in e or "sunset_at" not in e: raise RegistryError("INVALID_LIFECYCLE_METADATA",e["event_type"])
   if e["replacement_event"]==e["event_type"]: raise RegistryError("INVALID_LIFECYCLE_METADATA",e["event_type"])
  if e["replay_policy"] not in ("allowed","forbidden","requires-approval"): raise RegistryError("INVALID_REPLAY_POLICY",e["event_type"])
  if e["poison_policy"]["dlq_required"] and e["poison_policy"]["max_attempts"]<1: raise RegistryError("INVALID_POISON_POLICY",e["event_type"])
 return True
def main():
 schema,reg,fixture=load(SCHEMA),load(REGISTRY),load(FIXTURE)
 jsonschema.Draft202012Validator.check_schema(schema)
 v=jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker())
 errors=list(v.iter_errors(reg))
 if errors: raise SystemExit("registry schema: "+errors[0].message)
 validate(reg)
 for case in fixture["invalid_cases"]:
  x=copy.deepcopy(reg); m=case["mutation"]
  if m=="duplicate": x["events"].append(copy.deepcopy(x["events"][0]))
  elif m=="producer": x["events"][0]["producer_ids"]=[]
  elif m=="retention": x["events"][0]["retention_days"]=0
  elif m=="additive-major":
   x["events"][0]["schema_version"]="2.0"; x["events"][0]["compatibility"]={"change_class":"additive","compatible_with":["1.0"]}
  elif m=="breaking-major":
   x["events"][0]["schema_version"]="1.1"; x["events"][0]["compatibility"]={"change_class":"breaking","compatible_with":["1.0"]}
  elif m=="active-deprecated": x["events"][0]["deprecated_at"]="2026-11-02T00:00:00Z"
  elif m=="replay": x["events"][0]["replay_policy"]="always"
  try: validate(x); actual="ACCEPTED"
  except RegistryError as exc: actual=exc.code
  if actual!=case["expected_error"]: raise SystemExit(f'{case["case_id"]}: expected {case["expected_error"]}, got {actual}')
 for e in reg["events"]:
  schema_path=ROOT/"contracts/events"/e["payload_schema"]
  fixture_path=ROOT/e["fixture"]
  payload_schema=load(schema_path); jsonschema.Draft202012Validator.check_schema(payload_schema)
  event=load(fixture_path)
  if event["event_type"]!=e["event_type"] or event["schema_version"]!=e["schema_version"]: raise SystemExit("event fixture does not match registry "+e["event_type"])
  payload_v=jsonschema.Draft202012Validator(payload_schema,format_checker=jsonschema.FormatChecker())
  if list(payload_v.iter_errors(event["payload"])): raise SystemExit("payload fixture invalid "+e["event_type"])
 print(f'PASS: Event Registry schema + {len(reg["events"])} registered payload contracts + compatibility/lifecycle/producer/consumer/replay/retention policy + {len(fixture["invalid_cases"])} negative cases')
 print("LIMIT: only currently registered representative events are covered; consumer delivery semantics remain R03.38")
if __name__=="__main__": main()
