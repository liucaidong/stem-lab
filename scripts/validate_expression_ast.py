#!/usr/bin/env python3
"""Static Scientific Expression AST checker. It NEVER evaluates expression values."""
from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts/scientific-expression-ast.schema.v1alpha1.json"
FIXTURE_PATH = ROOT / "contracts/examples/scientific-expression.fixtures.v1alpha1.json"
UNIT_PATH = ROOT / "contracts/units/si-unit-registry.v1.json"
MAX_DEPTH, MAX_NODES, MAX_ARGS = 32, 512, 8
MAX_ABS_LITERAL, MAX_POWER_ABS = 1e100, 8
FUNCTIONS = {"abs": 1, "sqrt": 1, "exp": 1, "log": 1, "sin": 1, "cos": 1}
class ExpressionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)
def load(path: Path) -> Any:
    def reject(value: str): raise ValueError("non-JSON numeric constant: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)
def dim_add(a, b): return tuple(x+y for x,y in zip(a,b))
def dim_sub(a, b): return tuple(x-y for x,y in zip(a,b))
def dim_scale(a, n): return tuple(x*n for x in a)
def check_limits(node: Any, depth=1, count=None):
    if count is None: count=[0]
    count[0]+=1
    if depth>MAX_DEPTH: raise ExpressionError("DEPTH_LIMIT","AST depth limit exceeded")
    if count[0]>MAX_NODES: raise ExpressionError("NODE_LIMIT","AST node limit exceeded")
    if isinstance(node,dict):
        args=node.get("arguments",[])
        if len(args)>MAX_ARGS: raise ExpressionError("ARGUMENT_LIMIT","function argument limit exceeded")
        for value in node.values():
            if isinstance(value,(dict,list)): check_limits(value,depth+1,count)
    elif isinstance(node,list):
        for value in node: check_limits(value,depth+1,count)
def type_check(expr: dict, symbols: dict, units: dict):
    nodes=[0]
    def infer(node: dict):
        nodes[0]+=1
        if nodes[0]>MAX_NODES: raise ExpressionError("NODE_LIMIT","AST node limit exceeded")
        kind=node.get("kind")
        if kind=="constant":
            value=node.get("value")
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):
                raise ExpressionError("NON_FINITE_NUMBER","constant must be a finite JSON number")
            if abs(value)>MAX_ABS_LITERAL: raise ExpressionError("NUMERIC_RANGE","constant outside static numeric range")
            unit=units.get(node.get("unit_id"))
            if unit is None: raise ExpressionError("UNKNOWN_UNIT","constant references unknown unit")
            if node.get("quantity_kind") not in unit["quantity_kinds"]:
                raise ExpressionError("QUANTITY_KIND_MISMATCH","constant quantity kind not allowed by unit")
            if unit["offset_to_si"]!=0:
                raise ExpressionError("OFFSET_UNIT_UNSUPPORTED","offset units are unsupported in expression arithmetic")
            return (tuple(unit["dimension"]),node["quantity_kind"],value)
        if kind=="symbol":
            sid=node.get("symbol_id")
            item=symbols.get(sid)
            if item is None: raise ExpressionError("UNKNOWN_SYMBOL",f"unknown symbol: {sid}")
            unit=units.get(item.get("unit_id"))
            if unit is None: raise ExpressionError("UNKNOWN_UNIT",f"symbol {sid} has unknown unit")
            qk=item.get("quantity_kind")
            if qk not in unit["quantity_kinds"]: raise ExpressionError("QUANTITY_KIND_MISMATCH",f"symbol {sid} quantity kind/unit mismatch")
            if unit["offset_to_si"]!=0: raise ExpressionError("OFFSET_UNIT_UNSUPPORTED","offset units are unsupported")
            return (tuple(unit["dimension"]),qk,None)
        if kind=="unary":
            op=node.get("operator")
            if op not in ("negate","positive"): raise ExpressionError("UNSUPPORTED_OPERATOR",f"unsupported unary operator: {op}")
            d,q,v=infer(node["operand"])
            return (d,q,(-v if v is not None and op=="negate" else v))
        if kind=="binary":
            op=node.get("operator")
            if op not in ("add","subtract","multiply","divide","power"):
                raise ExpressionError("UNSUPPORTED_OPERATOR",f"unsupported binary operator: {op}")
            ld,lq,lv=infer(node["left"]); rd,rq,rv=infer(node["right"])
            if op in ("add","subtract"):
                if ld!=rd: raise ExpressionError("DIMENSION_MISMATCH","addition/subtraction requires identical dimensions")
                if lq!=rq: raise ExpressionError("QUANTITY_KIND_MISMATCH","addition/subtraction requires identical quantity kinds")
                return (ld,lq,None)
            if op=="multiply": return (dim_add(ld,rd),"derived",None)
            if op=="divide":
                if rv==0: raise ExpressionError("DIVISION_BY_ZERO","literal denominator is zero")
                return (dim_sub(ld,rd),"derived",None)
            if rd!=(0,0,0,0) or rq!="dimensionless" or rv is None or int(rv)!=rv or abs(rv)>MAX_POWER_ABS:
                raise ExpressionError("INVALID_POWER","power exponent must be a bounded dimensionless integer literal")
            return (dim_scale(ld,int(rv)),"derived",None)
        if kind=="call":
            fn=node.get("function")
            if fn not in FUNCTIONS: raise ExpressionError("UNREGISTERED_FUNCTION",f"function not allow-listed: {fn}")
            args=node.get("arguments",[])
            if len(args)!=FUNCTIONS[fn]: raise ExpressionError("ARGUMENT_COUNT","invalid function arity")
            d,q,v=infer(args[0])
            if fn=="abs": return (d,q,None)
            if fn=="sqrt":
                if any(x%2 for x in d): raise ExpressionError("DIMENSION_MISMATCH","sqrt requires even dimension exponents")
                return (tuple(x//2 for x in d),"derived",None)
            if d!=(0,0,0,0): raise ExpressionError("DIMENSION_MISMATCH",f"{fn} requires dimensionless input")
            return ((0,0,0,0),"dimensionless",None)
        raise ExpressionError("UNKNOWN_NODE","unknown AST node kind")
    check_limits(expr["root"])
    actual=infer(expr["root"])
    expected=expr["expected_type"]
    if tuple(expected["dimension"])!=actual[0]:
        raise ExpressionError("EXPECTED_DIMENSION_MISMATCH",f"expected {expected['dimension']}, inferred {list(actual[0])}")
    if expected["quantity_kind"]!="derived" and actual[1] not in (expected["quantity_kind"],"derived"):
        raise ExpressionError("EXPECTED_QUANTITY_KIND_MISMATCH",f"expected {expected['quantity_kind']}, inferred {actual[1]}")
    return actual
def main():
    schema, fixture, registry = load(SCHEMA_PATH), load(FIXTURE_PATH), load(UNIT_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator=jsonschema.Draft202012Validator(schema)
    units={u["unit_id"]:u for u in registry["units"]}
    errors=[]
    for item in fixture["valid"]:
        schema_errors=list(validator.iter_errors(item))
        if schema_errors: errors.append(f'{item["expression_id"]}: schema invalid: {schema_errors[0].message}'); continue
        try: type_check(item,fixture["symbol_table"],units)
        except ExpressionError as exc: errors.append(f'{item["expression_id"]}: {exc.code}: {exc}')
    for case in fixture["invalid"]:
        item=case["expression"]
        try:
            type_check(item,fixture["symbol_table"],units)
            actual="ACCEPTED"
        except ExpressionError as exc: actual=exc.code
        if actual!=case["expected_error"]:
            errors.append(f'{case["case_id"]}: expected {case["expected_error"]}, got {actual}')
    if errors: raise SystemExit("\n".join(errors))
    print(f'PASS: AST schema + {len(fixture["valid"])} valid expressions + {len(fixture["invalid"])} negative semantic cases; static only, no expression evaluation')
if __name__=="__main__": main()
