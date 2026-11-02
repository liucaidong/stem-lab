#!/usr/bin/env python3
"""Static Package Resource Graph validator; no fetching or resource execution."""
from __future__ import annotations
import json,re
from pathlib import Path
from urllib.parse import urlparse
from typing import Any
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/"contracts/package-resource-graph.schema.v1alpha1.json"
FIXTURE=ROOT/"contracts/examples/package-resource-graph.fixtures.v1alpha1.json"
class GraphError(Exception):
 def __init__(self,code,message): self.code=code; super().__init__(message)
def load(path):
 def reject(v): raise ValueError("non-JSON numeric constant: "+v)
 return json.loads(path.read_text(encoding="utf-8"),parse_constant=reject)
def validate_graph(graph):
 nodes=graph["nodes"]; by_id={}
 identities={}
 for n in nodes:
  rid=n["resource_id"]
  if rid in by_id:
   previous=by_id[rid]
   if (previous["resource_type"],previous["version"])==(n["resource_type"],n["version"]) and previous["digest"]!=n["digest"]:
    raise GraphError("CONFLICTING_RESOURCE_IDENTITY",rid)
   raise GraphError("DUPLICATE_RESOURCE_NODE",rid)
  by_id[rid]=n
  identity=(n["resource_type"],rid,n["version"])
  old=identities.get(identity)
  if old is not None and old!=n["digest"]: raise GraphError("CONFLICTING_RESOURCE_IDENTITY",rid)
  identities[identity]=n["digest"]
  storage=n["storage"]; uri=n.get("uri"); policy=n.get("access_policy_id")
  if storage=="embedded":
   if not uri or uri.startswith("/") or "\\\\" in uri or re.match(r"^[A-Za-z]:",uri) or any(x==".." for x in uri.split("/")):
    raise GraphError("UNSAFE_EMBEDDED_PATH",rid)
  elif storage=="external":
   parsed=urlparse(uri or "")
   if parsed.scheme!="https" or not parsed.hostname: raise GraphError("INVALID_EXTERNAL_URI",rid)
   if parsed.hostname.lower() not in {x.lower() for x in graph["policy"]["external_host_allowlist"]}:
    raise GraphError("EXTERNAL_HOST_NOT_ALLOWED",parsed.hostname)
  elif storage=="restricted":
   if not policy: raise GraphError("RESTRICTED_POLICY_REQUIRED",rid)
   if not graph["policy"]["allow_restricted_references"]: raise GraphError("RESTRICTED_REFERENCE_BLOCKED",rid)
 root=graph["root_resource_id"]
 if root not in by_id: raise GraphError("UNKNOWN_ROOT",root)
 adjacency={rid:[] for rid in by_id}; seen_edges=set()
 for e in graph["edges"]:
  src,dst=e["from"],e["to"]
  if src not in by_id or dst not in by_id: raise GraphError("DANGLING_REFERENCE",f"{src}->{dst}")
  key=(src,dst,e["relation"])
  if key in seen_edges: raise GraphError("DUPLICATE_EDGE",str(key))
  seen_edges.add(key); adjacency[src].append(dst)
 colors={rid:0 for rid in by_id}
 def visit(rid):
  if colors[rid]==1: raise GraphError("DEPENDENCY_CYCLE",rid)
  if colors[rid]==2: return
  colors[rid]=1
  for child in adjacency[rid]: visit(child)
  colors[rid]=2
 visit(root)
 reachable=set()
 stack=[root]
 while stack:
  rid=stack.pop()
  if rid in reachable: continue
  reachable.add(rid); stack.extend(adjacency[rid])
 if reachable!=set(by_id): raise GraphError("RESOURCE_OUTSIDE_CLOSURE",",".join(sorted(set(by_id)-reachable)))
 return reachable
def main():
 schema=load(SCHEMA); fixture=load(FIXTURE)
 jsonschema.Draft202012Validator.check_schema(schema)
 validator=jsonschema.Draft202012Validator(schema)
 errors=list(validator.iter_errors(fixture["valid_graph"]))
 if errors: raise SystemExit("valid graph schema failure: "+errors[0].message)
 validate_graph(fixture["valid_graph"])
 for case in fixture["invalid_cases"]:
  try: validate_graph(case["graph"]); actual="ACCEPTED"
  except GraphError as exc: actual=exc.code
  if actual!=case["expected_error"]: raise SystemExit(f'{case["case_id"]}: expected {case["expected_error"]}, got {actual}')
 print(f'PASS: Package Resource Graph schema + closure/reference/cycle/policy checks + {len(fixture["invalid_cases"])} negative cases; static only')
if __name__=="__main__": main()
