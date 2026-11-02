#!/usr/bin/env python3
"""Cross-module architecture inventory and consistency audit."""
from __future__ import annotations
import json
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"contracts/engineering-integration-audit.v1alpha1.json"
SCHEMA=ROOT/"contracts/engineering-integration-audit.schema.v1alpha1.json"
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def main():
 report,schema=load(REPORT),load(SCHEMA)
 jsonschema.Draft202012Validator.check_schema(schema)
 errors=list(jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker()).iter_errors(report))
 if errors: raise SystemExit("audit report schema: "+errors[0].message)
 model=load(ROOT/"contracts/scientific-model.schema.v1alpha1.json")
 ast=load(ROOT/"contracts/scientific-expression-ast.schema.v1alpha1.json")
 if model["properties"]["spec"]["properties"]["expressionLanguage"]["const"]!=ast["properties"]["language_id"]["const"]:
  raise SystemExit("ScientificModel expressionLanguage does not match AST language_id")
 graph=load(ROOT/"contracts/package-resource-graph.schema.v1alpha1.json")
 if "expression" not in graph["$defs"]["node"]["properties"]["resource_type"]["enum"]:
  raise SystemExit("Resource Graph lacks expression resource type")
 execution=load(ROOT/"contracts/runtime-execution-contract.schema.v1alpha1.json")
 expected={"queued","leased","running","succeeded","failed","timed_out","cancelled","rejected"}
 if set(execution["properties"]["execution_state"]["enum"])!=expected:
  raise SystemExit("Runtime Execution state enum diverges from R03.15")
 unit=load(ROOT/"contracts/units/si-unit-registry.v1.json")
 if not unit.get("units") or any(len(u.get("dimension",[]))!=4 for u in unit["units"]):
  raise SystemExit("Unit Registry dimension vector does not match four-axis contract")
 events=load(ROOT/"contracts/events/registry.v1.json")
 if len(events["events"])<1: raise SystemExit("Event Registry is empty")
 commands=load(ROOT/"contracts/commands/registry.v1alpha1.json")
 payload=load(ROOT/"contracts/commands/runtime-command-payloads.schema.v1alpha1.json")
 for command in commands["commands"]:
  ref=command["payload_schema_ref"].split("/")[-1]
  if ref not in payload["$defs"]: raise SystemExit("Command payload reference missing: "+ref)
 workflow=(ROOT/".github/workflows/contract-validation.yml").read_text()
 required=["validate_expression_ast.py","validate_package_resource_graph.py","validate_package_canonical_manifest.py","validate_package_governance.py","validate_event_registry.py","test_event_delivery_sqlite.py","test_postgres_transaction_rls.py","validate_api_operational_semantics.py","validate_runtime_execution_contract.py","test_solver_numerical_reference.py","validate_visualization_instrument_contract.py","test_worker_runtime.py","test_worker_pool.py","test_process_lifecycle.py"]
 missing=[p for p in required if p not in workflow]
 if missing: raise SystemExit("CI missing validators: "+", ".join(missing))
 if not (ROOT/"runtime/worker_runtime.py").exists(): raise SystemExit("missing Worker Runtime reference core")
 if not (ROOT/"runtime/worker_pool.py").exists(): raise SystemExit("missing Worker Pool reference core")
 if not (ROOT/"runtime/process_lifecycle.py").exists(): raise SystemExit("missing process lifecycle reference core")
 for p in ["contracts/experiment-package.schema.v1alpha1.json","contracts/package-canonical-manifest.schema.v1alpha1.json","contracts/package-attestation.schema.v1alpha1.json","contracts/package-provenance.schema.v1alpha1.json","contracts/package-license-record.schema.v1alpha1.json","contracts/runtime-event-envelope.schema.v1.json","contracts/visualization-instrument-contract.schema.v1alpha1.json"]:
  if not (ROOT/p).exists(): raise SystemExit("missing contract asset "+p)
 print(f'PASS: cross-module consistency inventory + {len(report["checks"])} audit checks + {len(report["findings"])} recorded findings')
 print("RESULT: "+report["result"]+"; production_ready="+str(report["readiness"]["production_ready"]))
if __name__=="__main__": main()
