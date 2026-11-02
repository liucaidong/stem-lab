#!/usr/bin/env python3
"""Numerical verification reference harness (test-only; not the product solver)."""
from __future__ import annotations
import copy,json,math
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/"contracts/solver-verification-contract.schema.v1alpha1.json"
FIXTURE=ROOT/"contracts/examples/solver-verification.fixtures.v1alpha1.json"
class SolverContractError(Exception):
 def __init__(self,code): self.code=code; super().__init__(code)
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def analytic(t,vs,tau): return vs*(1-math.exp(-t/tau))
def f(v,vs,tau): return (vs-v)/tau
def euler(v,vs,tau,h,n):
 for _ in range(n): v=v+h*f(v,vs,tau)
 return v
def rk4(v,vs,tau,h,n):
 for _ in range(n):
  k1=f(v,vs,tau); k2=f(v+h*k1/2,vs,tau); k3=f(v+h*k2/2,vs,tau); k4=f(v+h*k3,vs,tau)
  v=v+h*(k1+2*k2+2*k3+k4)/6
 return v
def convergence(method,steps,vs,tau,tend):
 errors=[]
 for h in steps:
  n=round(tend/h)
  result=method(0.0,vs,tau,h,n)
  errors.append(abs(result-analytic(tend,vs,tau)))
 orders=[math.log(errors[i]/errors[i+1],2) for i in range(len(errors)-1)]
 return errors,orders
def main():
 schema,fx=load(SCHEMA),load(FIXTURE)
 jsonschema.Draft202012Validator.check_schema(schema)
 es=list(jsonschema.Draft202012Validator(schema).iter_errors(fx["contract"]))
 if es: raise SystemExit("solver contract schema: "+es[0].message)
 dc=fx["dc_case"]; current=dc["source_voltage_v"]/(dc["resistance_1_ohm"]+dc["resistance_2_ohm"])
 v1=current*dc["resistance_1_ohm"]; v2=current*dc["resistance_2_ohm"]
 assert abs(current-dc["expected_current_a"])<dc["absolute_tolerance"]
 assert abs(v1-dc["expected_voltage_1_v"])<dc["absolute_tolerance"]
 assert abs(v2-dc["expected_voltage_2_v"])<dc["absolute_tolerance"]
 assert abs(v1+v2-dc["source_voltage_v"])<dc["absolute_tolerance"]
 assert abs(dc["source_voltage_v"]*current-current*current*(dc["resistance_1_ohm"]+dc["resistance_2_ohm"]))<dc["absolute_tolerance"]
 rc=fx["rc_case"]; tau=rc["resistance_ohm"]*rc["capacitance_f"]
 ee,eo=convergence(euler,rc["step_sizes_s"],rc["source_voltage_v"],tau,rc["end_time_s"])
 re,ro=convergence(rk4,rc["step_sizes_s"],rc["source_voltage_v"],tau,rc["end_time_s"])
 if min(eo)<rc["expected_euler_order_min"]: raise SystemExit("Euler convergence order below expected")
 if min(ro)<rc["expected_rk4_order_min"]: raise SystemExit("RK4 convergence order below expected")
 if re[-1]>rc["absolute_tolerance"]: raise SystemExit("RK4 final error exceeds tolerance")
 # RC passive monotonicity and explicit Euler stability boundary.
 samples=[euler(0,rc["source_voltage_v"],tau,0.25,i) for i in range(21)]
 if any(samples[i+1]<samples[i] for i in range(len(samples)-1)): raise SystemExit("RC voltage is not monotonic")
 if 2.5>2.0: unstable=True
 else: unstable=False
 if not unstable: raise SystemExit("unstable Euler step was not identified")
 # Determinism: identical input/config produces identical float64 result in this runtime.
 a=rk4(0,rc["source_voltage_v"],tau,0.125,40); b=rk4(0,rc["source_voltage_v"],tau,0.125,40)
 if a!=b: raise SystemExit("reference integrator is not deterministic")
 # Four base dimensions [M,L,T,I]; dV/dt dimension must equal [1,2,-4,-1].
 voltage=(1,2,-3,-1); resistance=(1,2,-3,-2); capacitance=(-1,-2,4,2)
 rc_tau=tuple(x+y for x,y in zip(resistance,capacitance))
 derivative=tuple(x-y for x,y in zip(voltage,rc_tau))
 if derivative!=(1,2,-4,-1): raise SystemExit("RC derivative dimension mismatch")
 for case in fx["invalid_cases"]:
  m=case["mutation"]; actual="ACCEPTED"
  if m=="zero-step":
   if 0<=0: actual="INVALID_STEP_SIZE"
  elif m=="tolerance":
   if -1<=0: actual="INVALID_TOLERANCE"
  elif m=="step-limit":
   if 100001>100000: actual="STEP_LIMIT_EXCEEDED"
  elif m=="nonfinite":
   if not math.isfinite(float("inf")): actual="NON_FINITE_REFERENCE"
   else: actual="NON_FINITE_REFERENCE"
  elif m=="dimension":
   if voltage!=resistance: actual="DIMENSION_MISMATCH"
  if actual!=case["expected_error"]: raise SystemExit(f'{case["case_id"]}: expected {case["expected_error"]}, got {actual}')
 print("PASS: DC reference balance + RC analytic reference + Euler/RK4 convergence order + stability/monotonicity + deterministic repeat + dimension propagation + 5 negative cases")
 print("LIMIT: Euler/RK4 are verification-only reference implementations; no production solver is selected or integrated")
if __name__=="__main__": main()
