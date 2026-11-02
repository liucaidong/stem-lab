#!/usr/bin/env python3
"""Static Runtime execution/lease/time/quota/checkpoint contract checks."""
from __future__ import annotations
import copy,json
from datetime import datetime
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/"contracts/runtime-execution-contract.schema.v1alpha1.json"
FIXTURE=ROOT/"contracts/examples/runtime-execution-contract.fixtures.v1alpha1.json"
class RuntimeErrorCode(Exception):
 def __init__(self,code): self.code=code; super().__init__(code)
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def dt(v): return datetime.fromisoformat(v.replace("Z","+00:00"))
def validate(x,now):
 lease=x["worker_lease"]; policy=x["policy"]; clock=x["clock"]; cp=x["checkpoint_policy"]; replay=x["replay_policy"]
 if lease["epoch"]<1 or lease["fencing_token"]<1: raise RuntimeErrorCode("INVALID_FENCING_TOKEN")
 if dt(lease["expires_at"])<=dt(now) or dt(lease["expires_at"])<=dt(lease["issued_at"]): raise RuntimeErrorCode("LEASE_EXPIRED")
 if dt(clock["wall_clock_deadline_at"])<=dt(clock["wall_clock_started_at"]): raise RuntimeErrorCode("INVALID_WALL_CLOCK_DEADLINE")
 if policy["wall_clock_timeout_ms"]<1 or policy["cpu_time_limit_ms"]<1 or policy["memory_limit_mb"]<16 or policy["output_limit_bytes"]<1024 or policy["max_steps"]<1: raise RuntimeErrorCode("INVALID_RESOURCE_QUOTA")
 if clock["simulation_time_start"]<0: raise RuntimeErrorCode("INVALID_SIMULATION_TIME")
 if cp["enabled"] and ("interval_steps" not in cp or "max_checkpoints" not in cp): raise RuntimeErrorCode("CHECKPOINT_INTERVAL_REQUIRED")
 if not cp["enabled"] and cp["resume_policy"]!="disabled": raise RuntimeErrorCode("INVALID_CHECKPOINT_POLICY")
 if replay["deterministic"] and "seed" not in replay: raise RuntimeErrorCode("DETERMINISTIC_REPLAY_SEED_REQUIRED")
 return True
def main():
 schema,fixture=load(SCHEMA),load(FIXTURE)
 jsonschema.Draft202012Validator.check_schema(schema)
 v=jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker())
 es=list(v.iter_errors(fixture["valid_execution"]))
 if es: raise SystemExit("valid execution schema: "+es[0].message)
 validate(fixture["valid_execution"],fixture["now"])
 for case in fixture["invalid_cases"]:
  x=copy.deepcopy(fixture["valid_execution"]); m=case["mutation"]
  if m=="lease": x["worker_lease"]["expires_at"]="2026-11-02T06:00:10Z"
  elif m=="deadline": x["clock"]["wall_clock_deadline_at"]="2026-11-02T05:59:00Z"
  elif m=="timeout": x["policy"]["wall_clock_timeout_ms"]=0
  elif m=="memory": x["policy"]["memory_limit_mb"]=8
  elif m=="seed": del x["replay_policy"]["seed"]
  elif m=="checkpoint": del x["checkpoint_policy"]["interval_steps"]
  elif m=="fencing": x["worker_lease"]["fencing_token"]=0
  elif m=="simtime": x["clock"]["simulation_time_start"]=-1
  try: validate(x,fixture["now"]); actual="ACCEPTED"
  except RuntimeErrorCode as e: actual=e.code
  if actual!=case["error"]: raise SystemExit(f'{case["case_id"]}: expected {case["error"]}, got {actual}')
 print(f'PASS: Runtime Execution Contract schema + lease/epoch/fencing/time/quota/checkpoint/replay rules + {len(fixture["invalid_cases"])} negative cases')
 print("LIMIT: no worker, scheduler, solver, checkpoint store or runtime process was executed")
if __name__=="__main__": main()
