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
from openapi_spec_validator import OpenAPIV31SpecValidator, validate as validate_openapi

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
    unit_schema = load_json("contracts/units/unit-registry.schema.v1.json")
    unit_registry = load_json("contracts/units/si-unit-registry.v1.json")
    jsonschema.Draft202012Validator.check_schema(package_schema)
    jsonschema.Draft202012Validator.check_schema(event_schema)
    jsonschema.Draft202012Validator.check_schema(model_schema)
    jsonschema.Draft202012Validator.check_schema(observation_schema)
    jsonschema.Draft202012Validator.check_schema(unit_schema)
    unit_validator = jsonschema.Draft202012Validator(
        unit_schema, format_checker=jsonschema.FormatChecker()
    )
    require(not list(unit_validator.iter_errors(unit_registry)),
            "Unit registry fixture must validate")
    require(not unit_registry_semantic_errors(unit_registry),
            "Unit registry IDs, dimensions, scales, and dimensional identities must validate")
    units_by_id = {item["unit_id"]: item for item in unit_registry["units"]}
    invalid_registry = copy.deepcopy(unit_registry)
    invalid_registry["units"].append(copy.deepcopy(invalid_registry["units"][0]))
    require(bool(unit_registry_semantic_errors(invalid_registry)),
            "Unit registry with duplicate unit_id must be rejected")

    package_validator = jsonschema.Draft202012Validator(
        package_schema, format_checker=jsonschema.FormatChecker()
    )
    valid_package = load_json("contracts/examples/experiment-package.valid.json")
    model_fixture = load_json("contracts/examples/scientific-model.dc-series.valid.json")
    invalid_package = load_json("contracts/examples/experiment-package.invalid.json")
    require(not list(package_validator.iter_errors(valid_package)),
            "Package positive fixture must validate")
    invalid_grade_band = copy.deepcopy(valid_package)
    invalid_grade_band["metadata"]["gradeBand"] = {"min": 12, "max": 6}
    require(bool(package_semantic_errors(invalid_grade_band, model_fixture)),
            "Package with inverted gradeBand must be rejected")
    invalid_model_reference = copy.deepcopy(valid_package)
    invalid_model_reference["spec"]["model"]["id"] = "unknown-model"
    require(bool(package_semantic_errors(invalid_model_reference, model_fixture)),
            "Package with unresolved model reference must be rejected")
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
    event_registry = load_json("contracts/events/registry.v1.json")
    registry_keys = [
        (item["event_type"], item["schema_version"])
        for item in event_registry["events"]
    ]
    require(len(registry_keys) == len(set(registry_keys)),
            "Event registry event_type/schema_version pairs must be unique")
    for event_definition in event_registry["events"]:
        payload_schema = load_json(
            "contracts/events/" + event_definition["payload_schema"]
        )
        jsonschema.Draft202012Validator.check_schema(payload_schema)
        event_fixture = load_json(event_definition["fixture"])
        require(event_fixture["event_type"] == event_definition["event_type"],
                "Event fixture type must match registry")
        require(event_fixture["schema_version"] == event_definition["schema_version"],
                "Event fixture version must match registry")
        require(not list(event_validator.iter_errors(event_fixture)),
                "Event envelope fixture must validate")
        payload_validator = jsonschema.Draft202012Validator(
            payload_schema, format_checker=jsonschema.FormatChecker()
        )
        require(not list(payload_validator.iter_errors(event_fixture["payload"])),
                "Event payload fixture must validate against its type schema")
        invalid_payload = copy.deepcopy(event_fixture["payload"])
        if event_definition["event_type"] == "SessionStarted":
            invalid_payload.pop("fencing_token", None)
        elif event_definition["event_type"] == "ExecutionSucceeded":
            invalid_payload["output_digest"] = "not-a-sha256-digest"
        elif event_definition["event_type"] == "ObservationRecorded":
            invalid_payload["data"]["value_ref"] = {
                "uri": "https://assets.example.invalid/data.bin",
                "digest": "sha256:" + "a" * 64,
                "size_bytes": 1
            }
        require(bool(list(payload_validator.iter_errors(invalid_payload))),
                "Invalid typed Event payload must be rejected")
    model_validator = jsonschema.Draft202012Validator(
        model_schema, format_checker=jsonschema.FormatChecker()
    )
    require(not list(model_validator.iter_errors(model_fixture)),
            "Scientific Model positive fixture must validate")
    require(not scientific_model_semantic_errors(model_fixture),
            "Scientific Model semantic references and parameter ranges must validate")
    require(not model_unit_semantic_errors(model_fixture, units_by_id),
            "Scientific Model parameter/variable units must match registered quantity kinds")
    invalid_model_unit = copy.deepcopy(model_fixture)
    invalid_model_unit["spec"]["parameters"][1]["unit"] = "V"
    require(bool(model_unit_semantic_errors(invalid_model_unit, units_by_id)),
            "Scientific Model with dimensionally incompatible unit must be rejected")
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
    require(not observation_semantic_errors(observation, model_fixture, valid_package, units_by_id),
            "Observation references and unit must match the pinned Package and Model")
    invalid_quantity = copy.deepcopy(observation)
    invalid_quantity["metadata"]["quantityId"] = "unknown-quantity"
    require(bool(observation_semantic_errors(invalid_quantity, model_fixture, valid_package, units_by_id)),
            "Observation with unknown quantity must be rejected")
    invalid_unit = copy.deepcopy(observation)
    invalid_unit["metadata"]["unit"] = "V"
    require(bool(observation_semantic_errors(invalid_unit, model_fixture, valid_package, units_by_id)),
            "Observation unit inconsistent with Model quantity must be rejected")
    invalid_model_version = copy.deepcopy(observation)
    invalid_model_version["metadata"]["modelVersion"] = "9.9.9"
    require(bool(observation_semantic_errors(invalid_model_version, model_fixture, valid_package, units_by_id)),
            "Observation with unpinned Model version must be rejected")
    invalid_observation = copy.deepcopy(observation)
    invalid_observation["data"]["valueRef"] = {
        "uri": "https://assets.example.invalid/data.bin",
        "digest": "sha256:" + "a" * 64,
        "sizeBytes": 1
    }
    require(bool(list(observation_validator.iter_errors(invalid_observation))),
            "Observation with both scalar value and valueRef must be rejected")
    print("PASS: Draft 2020-12 Schema, Unit Registry/dimensions, typed Event payloads, Package/Model/Observation semantics, and negative fixtures")


def unit_registry_semantic_errors(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    units = registry["units"]
    unit_ids = [item["unit_id"] for item in units]
    if len(unit_ids) != len(set(unit_ids)):
        errors.append("unit_id values must be unique")
    by_id = {item["unit_id"]: item for item in units}
    expected_dimensions = {
        "V": [1, 2, -3, -1],
        "A": [0, 0, 0, 1],
        "ohm": [1, 2, -3, -2],
        "W": [1, 2, -3, 0],
        "F": [-1, -2, 4, 2],
        "s": [0, 0, 1, 0],
        "1": [0, 0, 0, 0],
    }
    for unit in units:
        if len(unit["dimension"]) != 4:
            errors.append(f"{unit['unit_id']}: dimension vector must have four exponents")
        if not math.isfinite(unit["scale_to_si"]) or unit["scale_to_si"] <= 0:
            errors.append(f"{unit['unit_id']}: scale_to_si must be finite and positive")
        if not math.isfinite(unit["offset_to_si"]):
            errors.append(f"{unit['unit_id']}: offset_to_si must be finite")
        expected = expected_dimensions.get(unit["unit_id"])
        if expected is not None and unit["dimension"] != expected:
            errors.append(f"{unit['unit_id']}: canonical SI dimension vector mismatch")
    if all(key in by_id for key in ("V", "A", "ohm", "W", "F", "s")):
        subtract = lambda left, right: [
            a - b for a, b in zip(left, right)
        ]
        add = lambda left, right: [
            a + b for a, b in zip(left, right)
        ]
        if subtract(by_id["V"]["dimension"], by_id["A"]["dimension"]) != by_id["ohm"]["dimension"]:
            errors.append("ohm dimension must equal V/A")
        if add(by_id["V"]["dimension"], by_id["A"]["dimension"]) != by_id["W"]["dimension"]:
            errors.append("watt dimension must equal V*A")
        if add(by_id["ohm"]["dimension"], by_id["F"]["dimension"]) != by_id["s"]["dimension"]:
            errors.append("second dimension must equal ohm*farad")
    return errors


def model_unit_semantic_errors(
    model: dict[str, Any], units_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    spec = model["spec"]
    for item in spec["parameters"] + spec["variables"]:
        unit = units_by_id.get(item["unit"])
        if unit is None:
            errors.append(f"{item['id']}: unknown unit_id {item['unit']}")
        elif item["quantityKind"] not in unit["quantity_kinds"]:
            errors.append(
                f"{item['id']}: quantityKind {item['quantityKind']} is incompatible with {item['unit']}"
            )
    for initial in spec["initialConditions"]:
        if initial["unit"] not in units_by_id:
            errors.append(f"initial condition references unknown unit_id {initial['unit']}")
    return errors


def require_quantity_unit(
    unit_id: str,
    quantity_kind: str,
    label: str,
    units_by_id: dict[str, dict[str, Any]],
) -> None:
    unit = units_by_id.get(unit_id)
    require(unit is not None, f"{label}: unknown unit_id {unit_id}")
    require(quantity_kind in unit["quantity_kinds"],
            f"{label}: unit {unit_id} is incompatible with {quantity_kind}")


def package_semantic_errors(
    package: dict[str, Any], model: dict[str, Any] | None = None
) -> list[str]:
    errors: list[str] = []
    grade_band = package["metadata"].get("gradeBand", {})
    minimum = grade_band.get("min")
    maximum = grade_band.get("max")
    if minimum is not None and maximum is not None and minimum > maximum:
        errors.append("gradeBand.min must not exceed gradeBand.max")
    if model is not None:
        model_ref = package["spec"]["model"]
        if model_ref["id"] != model["metadata"]["id"]:
            errors.append("Package model ID does not match resolved Model")
        if model_ref["version"] != model["metadata"]["version"]:
            errors.append("Package model version does not match resolved Model")
    return errors


def observation_semantic_errors(
    observation: dict[str, Any],
    model: dict[str, Any],
    package: dict[str, Any],
    units_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    metadata = observation["metadata"]
    errors: list[str] = []
    if metadata["packageId"] != package["metadata"]["id"]:
        errors.append("Observation package ID does not match pinned Package")
    if metadata["packageVersion"] != package["metadata"]["version"]:
        errors.append("Observation package version does not match pinned Package")
    if metadata["modelId"] != model["metadata"]["id"]:
        errors.append("Observation Model ID does not match resolved Model")
    if metadata["modelVersion"] != model["metadata"]["version"]:
        errors.append("Observation Model version does not match resolved Model")
    variables = {item["id"]: item for item in model["spec"]["variables"]}
    quantity = variables.get(metadata["quantityId"])
    if quantity is None:
        errors.append("Observation quantityId does not exist in Model variables")
    elif quantity["unit"] != metadata["unit"]:
        errors.append("Observation unit does not match Model variable unit")
    unit = units_by_id.get(metadata["unit"])
    if unit is None:
        errors.append("Observation references unknown unit_id")
    elif quantity is not None and quantity["quantityKind"] not in unit["quantity_kinds"]:
        errors.append("Observation unit is incompatible with Model quantityKind")
    return errors


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
    validate_openapi(document, cls=OpenAPIV31SpecValidator)
    validate_openapi_semantics(document)
    print("PASS: OpenAPI 3.1 specification and API security/idempotency/pagination semantics")


def validate_openapi_semantics(document: dict[str, Any]) -> None:
    require({"bearerAuth": []} in document.get("security", []),
            "All API operations must inherit bearerAuth security")
    components = document["components"]
    schemas = components["schemas"]
    for schema_name in ("CreateSessionRequest", "RuntimeCommandRequest"):
        properties = schemas[schema_name].get("properties", {})
        require("tenant_id" not in properties and "actor_id" not in properties,
                f"{schema_name} must not accept client-supplied tenant/actor identity")

    paths = document["paths"]
    create_session = paths["/sessions"]["post"]
    submit_command = paths["/sessions/{session_id}/commands"]["post"]
    for operation_name, operation in (
        ("createSession", create_session),
        ("submitRuntimeCommand", submit_command),
    ):
        header_names = {
            item.get("name")
            for item in operation.get("parameters", [])
            if item.get("in") == "header"
        }
        require("Idempotency-Key" in header_names,
                f"{operation_name} must require Idempotency-Key")
    command_headers = {
        item.get("name")
        for item in submit_command.get("parameters", [])
        if item.get("in") == "header"
    }
    require("If-Match" in command_headers,
            "submitRuntimeCommand must require If-Match")
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in {
                "get", "post", "put", "patch", "delete", "options", "head", "trace"
            }:
                continue
            require("401" in operation["responses"],
                    f"{method.upper()} {path} must declare 401")
    observation_list = paths["/sessions/{session_id}/observations"]["get"]
    limit = next(
        (item for item in observation_list.get("parameters", [])
         if item.get("name") == "limit" and item.get("in") == "query"),
        None,
    )
    require(limit is not None, "Observation listing must define limit")
    limit_schema = limit["schema"]
    require(limit_schema.get("minimum") == 1
            and limit_schema.get("maximum") == 500
            and limit_schema.get("default") == 100,
            "Observation limit must remain bounded to 1..500 with default 100")
    observation_schema = schemas["Observation"]
    require(observation_schema["properties"]["simulation_time"].get("minimum") == 0,
            "Observation simulation_time must be non-negative")
    value_ref = observation_schema["properties"]["value_ref"]
    require("size_bytes" in value_ref.get("required", [])
            and value_ref["properties"]["size_bytes"].get("type") == "integer"
            and value_ref["properties"]["size_bytes"].get("minimum") == 0,
            "Observation value_ref must require non-negative size_bytes")
    require("error" in schemas["ErrorEnvelope"].get("required", [])
            and "code" in schemas["Error"].get("required", [])
            and "correlation_id" in schemas["Error"].get("required", []),
            "Error responses must use a machine-readable correlated ErrorEnvelope")
    retry_after = components["responses"]["TooManyRequests"].get("headers", {}).get("Retry-After")
    require(retry_after is not None,
            "429 TooManyRequests must expose Retry-After")
    print("PASS: API security, identity boundary, idempotency, optimistic concurrency, pagination bounds, and error semantics")


def close(actual: float, expected: float, label: str) -> None:
    # Floating-point comparison tolerance for these deterministic fixtures only.
    # It is not a solver acceptance tolerance or a measurement uncertainty model.
    require(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12),
            f"{label}: expected {expected}, got {actual}")


def validate_dc_reference_cases() -> None:
    unit_registry = load_json("contracts/units/si-unit-registry.v1.json")
    units_by_id = {item["unit_id"]: item for item in unit_registry["units"]}
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
        require_quantity_unit(source["unit"], "electric-potential", f"{case_id} source voltage", units_by_id)
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
            require_quantity_unit(resistor["unit"], "electric-resistance",
                                  f"{case_id} resistor", units_by_id)
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
        require_quantity_unit(expected["equivalent_resistance"]["unit"],
                              "electric-resistance", f"{case_id} equivalent resistance", units_by_id)
        require_quantity_unit(expected["current"]["unit"],
                              "electric-current", f"{case_id} current", units_by_id)

        drops = expected["voltage_drops"]
        require(len(drops) == len(resistors),
                f"{case_id}: voltage drop count must match resistor count")
        drop_sum = 0.0
        for resistor, drop in zip(resistors, drops):
            require(drop["resistor_id"] == resistor["id"],
                    f"{case_id}: voltage drop resistor ordering/reference mismatch")
            require_quantity_unit(drop["unit"], "electric-potential",
                                  f"{case_id} voltage drop", units_by_id)
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
        require_quantity_unit(expected["source_power"]["unit"], "power",
                              f"{case_id} source power", units_by_id)
        close(source_power, resistor_power, f"{case_id} power balance")

    print(f"PASS: DC reference arithmetic, Ohm's law, KVL and power balance ({len(cases)} cases)")


def validate_rc_reference_cases() -> None:
    unit_registry = load_json("contracts/units/si-unit-registry.v1.json")
    units_by_id = {item["unit_id"]: item for item in unit_registry["units"]}
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
    require_quantity_unit(parameters["source_voltage"]["unit"], "electric-potential",
                          "RC source voltage", units_by_id)
    require_quantity_unit(parameters["resistance"]["unit"], "electric-resistance",
                          "RC resistance", units_by_id)
    require_quantity_unit(parameters["capacitance"]["unit"], "capacitance",
                          "RC capacitance", units_by_id)
    require_quantity_unit(parameters["time_constant"]["unit"], "time",
                          "RC time constant", units_by_id)
    require(all(math.isfinite(value) for value in (source, resistance, capacitance, tau)),
            "RC parameters and time constant must be finite")
    require(source > 0 and resistance > 0 and capacitance > 0,
            "RC parameters must be positive")

    cases = document.get("cases")
    require(isinstance(cases, list) and len(cases) >= 2,
            "RC reference cases must contain multiple time samples")
    previous_vc = -math.inf
    previous_current = math.inf
    previous_time = -math.inf
    for case in cases:
        case_id = case["case_id"]
        time_value = float(case["time"]["value"])
        require_quantity_unit(case["time"]["unit"], "time", f"{case_id} time", units_by_id)
        require(math.isfinite(time_value) and time_value >= 0,
                f"{case_id}: time must be finite non-negative seconds")
        require(time_value > previous_time,
                f"{case_id}: RC sample times must be strictly increasing")
        previous_time = time_value
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
            quantity_kind = {"capacitor_voltage": "electric-potential",
                             "resistor_voltage": "electric-potential",
                             "current": "electric-current"}[quantity]
            require_quantity_unit(actual["unit"], quantity_kind,
                                  f"{case_id} {quantity}", units_by_id)
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
