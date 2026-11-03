#!/usr/bin/env python3
"""Static scene graph, timeline, and instrument binding contract validation."""
from __future__ import annotations
import copy,json
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/"contracts/visualization-instrument-contract.schema.v1alpha1.json"
FIXTURE=ROOT/"contracts/examples/visualization-instrument.fixtures.v1alpha1.json"
class VizError(Exception):
 def __init__(self,code): self.code=code; super().__init__(code)
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def validate(x):
 nodes=x["scene_graph"]["nodes"]; by_id={}
 for n in nodes:
  if n["node_id"] in by_id: raise VizError("DUPLICATE_SCENE_NODE")
  by_id[n["node_id"]]=n
 root=x["scene_graph"]["root_node_id"]
 if root not in by_id or by_id[root]["node_type"]!="root": raise VizError("UNKNOWN_SCENE_ROOT")
 parents={}
 for n in nodes:
  p=n["parent_id"]
  if n["node_id"]==root:
   if p is not None: raise VizError("INVALID_SCENE_ROOT")
  elif p not in by_id: raise VizError("UNKNOWN_SCENE_PARENT")
  parents[n["node_id"]]=p
 for node_id in by_id:
  seen=set(); cur=node_id
  while cur is not None:
   if cur in seen: raise VizError("SCENE_GRAPH_CYCLE")
   seen.add(cur); cur=parents[cur]
 for track in x["timeline"]["tracks"]:
  if track["target_node_id"] not in by_id: raise VizError("UNKNOWN_TIMELINE_TARGET")
  if any(k["time"]>x["timeline"]["duration"] for k in track["keyframes"]): raise VizError("TIMELINE_KEYFRAME_OUT_OF_RANGE")
 for ins in x["instruments"]:
  if ins["node_id"] not in by_id: raise VizError("UNKNOWN_INSTRUMENT_NODE")
  if ins["unit_id"]!=ins["observation_binding"]["unit_id"]: raise VizError("INSTRUMENT_BINDING_UNIT_MISMATCH")
  lo,hi=ins["measurement_range"]
  if lo>=hi: raise VizError("INVALID_MEASUREMENT_RANGE")
  if ins["sampling_interval"]<=0: raise VizError("INVALID_SAMPLING_INTERVAL")
  if ins["observation_source_type"]!="instrument": raise VizError("INVALID_OBSERVATION_SOURCE")
  if x["timeline"]["time_domain"] not in ("simulation","wall-clock"): raise VizError("TIMELINE_TIME_DOMAIN_MISMATCH")
 return True
def main():
 schema,fx=load(SCHEMA),load(FIXTURE)
 jsonschema.Draft202012Validator.check_schema(schema)
 es=list(jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker()).iter_errors(fx["valid_contract"]))
 if es: raise SystemExit("valid visualization schema: "+es[0].message)
 validate(fx["valid_contract"])
 for case in fx["invalid_cases"]:
  x=copy.deepcopy(fx["valid_contract"]); m=case["mutation"]
  if m=="duplicate-node": x["scene_graph"]["nodes"].append(copy.deepcopy(x["scene_graph"]["nodes"][1]))
  elif m=="parent": x["scene_graph"]["nodes"][1]["parent_id"]="missing"
  elif m=="cycle": x["scene_graph"]["nodes"][1]["parent_id"]="meter"; x["scene_graph"]["nodes"][2]["parent_id"]="circuit"
  elif m=="timeline-target": x["timeline"]["tracks"][0]["target_node_id"]="missing"
  elif m=="timeline-time": x["timeline"]["tracks"][0]["keyframes"][-1]["time"]=6
  elif m=="instrument-node": x["instruments"][0]["node_id"]="missing"
  elif m=="unit": x["instruments"][0]["observation_binding"]["unit_id"]="A"
  elif m=="range": x["instruments"][0]["measurement_range"]=[12,0]
  elif m=="sampling": x["instruments"][0]["sampling_interval"]=0
  elif m=="time-domain": x["timeline"]["time_domain"]="mixed"
  try: validate(x); actual="ACCEPTED"
  except VizError as e: actual=e.code
  if actual!=case["error"]: raise SystemExit(f'{case["case_id"]}: expected {case["error"]}, got {actual}')
 print(f'PASS: Visualization/Instrument schema + scene graph parent/cycle + timeline + observation binding + {len(fx["invalid_cases"])} negative cases')
 print("LIMIT: no renderer, browser, GPU, scene execution or real instrument sampling was run")
if __name__=="__main__": main()
