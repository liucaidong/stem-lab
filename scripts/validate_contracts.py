#!/usr/bin/env python3
"""Repeatable draft contract checks; this is not a production runtime implementation."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> Any:
    path = ROOT / relative_path

    def reject_non_json_constant(value: str) -> None:
        raise ValueError(f"Non-JSON numeric constant {value!r} in {relative_path}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_non_json_constant)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_schema_and_fixtures() -> None:
    package_schema = load_json("contracts/experiment-package.schema.v1alpha1.json")
    event_schema = load_json("contracts/runtime-event-envelope.schema.v1.json")
    model_schema = load_json("contracts/scientific-model.schema.v1alpha1.json")
    observation_schema = load_json("contracts/observation.schema.v1alpha1.json")
    jsonschema.Draft202012Validator.check_schema(package_schema)
    jsonschema.Draft202012Validator.check_schema(event_schema)
    jsonschema.Draft202012Validator.check_schema(model_schema)
    jsonschema.Draft202012Validator.check_schema(observation_schema)

    package_validator = jsonschema.Draft202012Validator(
        package_schema, format_checker=jsonschema.FormatChecker()
    )
    valid_package = load_json("contracts/examples/experiment-package.valid.json")
    invalid_package = load_json("contracts/examples/experiment-package.invalid.json")
    require(not list(package_validator.iter_errors(valid_package)),
            "Package positive fixture must validate")
    invalid_errors = list(package_validator.iter_errors(invalid_package))
    require(bool(invalid_errors), "Package negative fixture must be rejected")
    error_paths = {"/" + "/".join(str(part) for part in error.absolute_path)
                   for error in invalid_errors}
    require("/spec/model" in error_paths,
            "Negative fixture must fail because model.digest is missing")
    require("/spec/runtime/allowedModes/0" in error_paths,
            "Negative fixture must fail because arbitrary-code is unsupported")

    event_validator = jsonschema.Draft202012Validator(
        event_schema, format_checker=jsonschema.FormatChecker()
    )
    event = load_json("contracts/examples/runtime-event.valid.json")
    require(not list(event_validator.iter_errors(event)),
            "Runtime Event positive fixture must validate")
    model_validator = jsonschema.Draft202012Validator(
        model_schema, format_checker=jsonschema.FormatChecker()
    )
    model_fixture = load_json("contracts/examples/scientific-model.dc-series.valid.json")
    require(not list(model_validator.iter_errors(model_fixture)),
            "Scientific Model positive fixture must validate")
    require(not scientific_model_semantic_errors(model_fixture),
            "Scientific Model semantic references and parameter ranges must validate")
    invalid_model = copy.deepcopy(model_fixture)
    invalid_model["spec"]["equations"][0]["inputs"][0] = "unknown-variable"
    require(bool(scientific_model_semantic_errors(invalid_model)),
            "Scientific Model with unknown equation reference must be rejected")
    invalid_range_model = copy.deepcopy(model_fixture)
    invalid_range_model["spec"]["parameters"][0]["maximum"] = -1
    require(bool(scientific_model_semantic_errors(invalid_range_model)),
            "Scientific Model with inverted parameter range must be rejected")

    observation_validator = jsonschema.Draft202012Validator(
        observation_schema, format_checker=jsonschema.FormatChecker()
    )
    observation = load_json("contracts/examples/observation.valid.json")
    require(not list(observation_validator.iter_errors(observation)),
            "Observation positive fixture must validate")
    invalid_observation = copy.deepcopy(observation)
    invalid_observation["data"]["valueRef"] = {
        "uri": "https://assets.example.invalid/data.bin",
        "digest": "sha256:" + "a" * 64,
        "sizeBytes": 1
    }
    require(bool(list(observation_validator.iter_errors(invalid_observation))),
            "Observation with both scalar value and valueRef must be rejected")
    print("PASS: Draft 2020-12 meta-schema checks, fixtures, and Model reference/range semantics")


def scientific_model_semantic_errors(model: dict[str, Any]) -> list[str]:
    spec = model["spec"]
    parameters = spec["parameters"]
    variables = spec["variables"]
    parameter_ids = [item["id"] for item in parameters]
    variable_ids = [item["id"] for item in variables]
    all_ids = parameter_ids + variable_ids
    errors: list[str] = []
    if len(all_ids) != len(set(all_ids)):
        errors.append("parameter/variable IDs must be globally unique")
    known_ids = set(all_ids)

    for parameter in parameters:
        minimum = parameter.get("minimum")
        maximum = parameter.get("maximum")
        default = parameter["defaultValue"]
        if minimum is not None and maximum is not None and minimum > maximum:
            errors.append(f"{parameter['id']}: minimum exceeds maximum")
        if minimum is not None and default < minimum:
            errors.append(f"{parameter['id']}: defaultValue is below minimum")
        if maximum is not None and default > maximum:
            errors.append(f"{parameter['id']}: defaultValue is above maximum")

    for equation in spec["equations"]:
        for reference in equation["inputs"] + equation["outputs"]:
            if reference not in known_ids:
                errors.append(f"{equation['id']}: unknown equation reference {reference}")
    for constraint in spec["constraints"]:
        for reference in constraint["targetIds"]:
            if reference not in known_ids:
                errors.append(f"{constraint['id']}: unknown constraint target {reference}")
    for initial in spec["initialConditions"]:
        if initial["variableId"] not in variable_ids:
            errors.append(f"unknown initial-condition variable {initial['variableId']}")
    return errors


def validate_openapi_yaml() -> None:
    document = yaml.safe_load(
        (ROOT / "contracts/openapi.v1.draft.yaml").read_text(encoding="utf-8")
    )
    require(isinstance(document, dict), "OpenAPI YAML root must be a mapping")
    require(document.get("openapi") == "3.1.0",
            "OpenAPI document must declare version 3.1.0")
    paths = document.get("paths")
    require(isinstance(paths, dict) and bool(paths), "OpenAPI paths must be non-empty")
    operation_count = 0
    for path, path_item in paths.items():
        require(isinstance(path_item, dict), f"Path item {path} must be a mapping")
        for method, operation in path_item.items():
            if method.lower() not in {
                "get", "post", "put", "patch", "delete", "options", "head", "trace"
            }:
                continue
            operation_count += 1
            require(isinstance(operation, dict), f"{method} {path} must be a mapping")
            require(bool(operation.get("operationId")),
                    f"{method} {path} must define operationId")
            require(isinstance(operation.get("responses"), dict)
                    and bool(operation["responses"]),
                    f"{method} {path} must define responses")
    require(operation_count == 4,
            f"Expected 4 draft operations, found {operation_count}")
    print("PASS: OpenAPI YAML parsing and limited structural assertions")
    print("NOTE: This does NOT replace an OpenAPI 3.1 specification validator")


def close(actual: float, expected: float, label: str) -> None:
    # Floating-point comparison tolerance for these deterministic fixtures only.
    # It is not a solver acceptance tolerance or a measurement uncertainty model.
    require(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12),
            f"{label}: expected {expected}, got {actual}")


def validate_dc_reference_cases() -> None:
    document = load_json("contracts/examples/dc-circuit.reference-cases.json")
    require(document.get("schema_version") == "0.1-draft",
            "Unexpected DC reference case version")
    require(set(document.get("assumptions", [])) >= {
        "ideal_constant_voltage_source", "ideal_positive_resistors",
        "ideal_wires", "steady_state", "no_instrument_loading"
    }, "DC model assumptions are incomplete")
    cases = document.get("cases")
    require(isinstance(cases, list) and len(cases) >= 1,
            "DC reference cases must be a non-empty list")

    for case in cases:
        case_id = case["case_id"]
        source = case["source_voltage"]
        require(source["unit"] == "V", f"{case_id}: source voltage unit must be V")
        voltage = float(source["value"])
        require(math.isfinite(voltage) and voltage >= 0,
                f"{case_id}: source voltage must be finite and non-negative")

        resistors = case["resistors"]
        require(isinstance(resistors, list) and len(resistors) >= 1,
                f"{case_id}: at least one resistor is required")
        ids = [item["id"] for item in resistors]
        require(len(ids) == len(set(ids)), f"{case_id}: resistor IDs must be unique")
        resistance_values = []
        for resistor in resistors:
            require(resistor["unit"] == "ohm",
                    f"{case_id}: resistance unit must be ohm")
            resistance = float(resistor["value"])
            require(math.isfinite(resistance) and resistance > 0,
                    f"{case_id}: resistance must be finite and positive")
            resistance_values.append(resistance)

        equivalent = sum(resistance_values)
        current = voltage / equivalent
        expected = case["expected"]
        close(float(expected["equivalent_resistance"]["value"]), equivalent,
              f"{case_id} equivalent resistance")
        close(float(expected["current"]["value"]), current, f"{case_id} current")
        require(expected["equivalent_resistance"]["unit"] == "ohm",
                f"{case_id}: equivalent resistance unit must be ohm")
        require(expected["current"]["unit"] == "A",
                f"{case_id}: current unit must be A")

        drops = expected["voltage_drops"]
        require(len(drops) == len(resistors),
                f"{case_id}: voltage drop count must match resistor count")
        drop_sum = 0.0
        for resistor, drop in zip(resistors, drops):
            require(drop["resistor_id"] == resistor["id"],
                    f"{case_id}: voltage drop resistor ordering/reference mismatch")
            require(drop["unit"] == "V", f"{case_id}: voltage drop unit must be V")
            calculated_drop = current * float(resistor["value"])
            close(float(drop["value"]), calculated_drop,
                  f"{case_id} {resistor['id']} voltage drop")
            drop_sum += float(drop["value"])
        close(drop_sum, voltage, f"{case_id} KVL")

        source_power = voltage * current
        resistor_power = sum(current * current * resistance
                             for resistance in resistance_values)
        close(float(expected["source_power"]["value"]), source_power,
              f"{case_id} source power")
        require(expected["source_power"]["unit"] == "W",
                f"{case_id}: source power unit must be W")
        close(source_power, resistor_power, f"{case_id} power balance")

    print(f"PASS: DC reference arithmetic, Ohm's law, KVL and power balance ({len(cases)} cases)")


def validate_rc_reference_cases() -> None:
    document = load_json("contracts/examples/rc-circuit.reference-cases.json")
    require(document.get("schema_version") == "0.1-draft",
            "Unexpected RC reference case version")
    parameters = document["parameters"]
    source = float(parameters["source_voltage"]["value"])
    resistance = float(parameters["resistance"]["value"])
    capacitance = float(parameters["capacitance"]["value"])
    tau = resistance * capacitance
    close(float(parameters["time_constant"]["value"]), tau,
          "RC time constant")
    require(parameters["source_voltage"]["unit"] == "V", "RC source unit must be V")
    require(parameters["resistance"]["unit"] == "ohm", "RC resistance unit must be ohm")
    require(parameters["capacitance"]["unit"] == "F", "RC capacitance unit must be F")
    require(source > 0 and resistance > 0 and capacitance > 0,
            "RC parameters must be positive")

    cases = document.get("cases")
    require(isinstance(cases, list) and len(cases) >= 2,
            "RC reference cases must contain multiple time samples")
    previous_vc = -math.inf
    previous_current = math.inf
    for case in cases:
        case_id = case["case_id"]
        time_value = float(case["time"]["value"])
        require(case["time"]["unit"] == "s" and time_value >= 0,
                f"{case_id}: time must be non-negative seconds")
        decay = math.exp(-time_value / tau)
        expected_values = {
            "capacitor_voltage": source * (1.0 - decay),
            "resistor_voltage": source * decay,
            "current": (source / resistance) * decay,
        }
        for quantity, calculated in expected_values.items():
            actual = case["expected"][quantity]
            unit = {"capacitor_voltage": "V", "resistor_voltage": "V",
                    "current": "A"}[quantity]
            require(actual["unit"] == unit, f"{case_id}: {quantity} unit mismatch")
            close(float(actual["value"]), calculated, f"{case_id} {quantity}")
        vc = float(case["expected"]["capacitor_voltage"]["value"])
        vr = float(case["expected"]["resistor_voltage"]["value"])
        current = float(case["expected"]["current"]["value"])
        close(vc + vr, source, f"{case_id} KVL")
        require(vc >= previous_vc, f"{case_id}: capacitor voltage must not decrease")
        require(current <= previous_current, f"{case_id}: charging current must not increase")
        previous_vc, previous_current = vc, current

    print(f"PASS: RC analytic charging reference, KVL and monotonicity ({len(cases)} samples)")


def main() -> None:
    validate_schema_and_fixtures()
    validate_openapi_yaml()
    validate_dc_reference_cases()
    validate_rc_reference_cases()
    print("RESULT: all configured draft checks passed; contract freeze is NOT implied")


if __name__ == "__main__":
    main()
