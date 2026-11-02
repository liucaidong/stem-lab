#!/usr/bin/env python3
"""Validation-only deterministic Package projection builder reference."""
from __future__ import annotations
import copy, json, re, sys, unicodedata
from pathlib import Path
from urllib.parse import urlparse
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA = ROOT / "contracts/experiment-package.schema.v1alpha1.json"
CATALOG_SCHEMA = ROOT / "contracts/package-resource-catalog-snapshot.schema.v1alpha1.json"
GRAPH_SCHEMA = ROOT / "contracts/package-resource-graph.schema.v1alpha1.json"
PROJECTION_SCHEMA = ROOT / "contracts/package-canonical-manifest.schema.v1alpha1.json"
FIXTURE = ROOT / "contracts/examples/package-projection-builder.fixtures.v1alpha1.json"

class ProjectionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

def load(path):
    def reject(value):
        raise ValueError("non-JSON numeric constant: " + value)
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate JSON property: " + key)
            out[key] = value
        return out
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject, object_pairs_hook=pairs)

def schema_validate(instance, schema_path, label):
    schema = load(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(instance))
    if errors:
        raise ProjectionError(label, errors[0].message)

def identity_key(identity):
    return (identity["resource_type"], identity["resource_id"], identity["version"])

def graph_id(identity):
    return identity["resource_type"] + ":" + identity["resource_id"]

def path_check(uri, storage, canonical_path):
    if (not canonical_path or canonical_path.startswith("/") or "\\" in canonical_path or
        re.match(r"^[A-Za-z]:", canonical_path) or
        any(part in ("", ".", "..") for part in canonical_path.split("/")) or
        unicodedata.normalize("NFC", canonical_path) != canonical_path):
        raise ProjectionError("RESOURCE_POLICY_REJECTED", "unsafe canonical resource path")
    if storage == "embedded":
        if (not uri or uri.startswith("/") or "\\" in uri or
            re.match(r"^[A-Za-z]:", uri) or
            any(part in ("", ".", "..") for part in uri.split("/"))):
            raise ProjectionError("RESOURCE_POLICY_REJECTED", "unsafe embedded path")
        if unicodedata.normalize("NFC", uri) != uri:
            raise ProjectionError("RESOURCE_POLICY_REJECTED", "non-NFC embedded path")
    elif storage == "external":
        parsed = urlparse(uri)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ProjectionError("RESOURCE_POLICY_REJECTED", "external URI must be HTTPS")
    elif storage == "restricted":
        if not uri:
            raise ProjectionError("RESOURCE_POLICY_REJECTED", "restricted URI missing")

def build_projection(manifest, catalog, source_manifest_digest, model_documents):
    """Pure function: no I/O, no mutation, no network, no execution."""
    original_manifest = copy.deepcopy(manifest)
    original_catalog = copy.deepcopy(catalog)
    schema_validate(manifest, MANIFEST_SCHEMA, "MANIFEST_SCHEMA_INVALID")
    schema_validate(catalog, CATALOG_SCHEMA, "CATALOG_SCHEMA_INVALID")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", source_manifest_digest or ""):
        raise ProjectionError("SOURCE_MANIFEST_DIGEST_REQUIRED", "valid source manifest digest required")

    policy = catalog["policy"]
    entries = {}
    for entry in catalog["resources"]:
        ident = entry["identity"]
        key = identity_key(ident)
        if key in entries:
            old = entries[key]
            if old["identity"]["digest"] != ident["digest"]:
                raise ProjectionError("CONFLICTING_CATALOG_DIGEST", str(key))
            raise ProjectionError("DUPLICATE_CATALOG_IDENTITY", str(key))
        path_check(entry["uri"], entry["storage"], entry["path"])
        if entry["storage"] == "external":
            host = urlparse(entry["uri"]).hostname.lower()
            if host not in {h.lower() for h in policy["external_host_allowlist"]}:
                raise ProjectionError("RESOURCE_POLICY_REJECTED", "external host not allowlisted")
        if entry["storage"] == "restricted":
            if not entry.get("access_policy_id") or not policy["allow_restricted_references"]:
                raise ProjectionError("RESOURCE_POLICY_REJECTED", "restricted resource blocked")
        entries[key] = entry

    package = manifest["metadata"]
    root_id = "package:" + package["id"] + "@" + package["version"]
    root_node = {
        "resource_id": root_id, "resource_type": "package",
        "version": package["version"], "digest": source_manifest_digest,
        "storage": "embedded", "uri": "manifest.json"
    }
    nodes = {root_id: root_node}
    edges = set()
    queue = []
    direct = []
    spec = manifest["spec"]
    role_refs = [
        ("model", spec["model"]), ("scene", spec["scene"]),
        *[("instrument", x) for x in spec["instruments"]],
        ("workflow", spec["workflow"]), ("rubric", spec["assessment"]["rubric"]),
        *[("asset", x) for x in spec["assets"]]
    ]
    for resource_type, ref in role_refs:
        if resource_type == "asset":
            candidates = [e for e in entries.values()
                          if e["identity"]["resource_type"] == "asset"
                          and e["identity"]["resource_id"] == ref["id"]
                          and e["identity"]["digest"] == ref["digest"]]
            if len(candidates) != 1:
                raise ProjectionError("RESOURCE_REF_NOT_FOUND", ref["id"])
            entry = candidates[0]
            if (entry["media_type"] != ref["mediaType"] or
                entry["license_id"] != ref["licenseId"] or
                ("sizeBytes" in ref and entry["size_bytes"] != ref["sizeBytes"])):
                raise ProjectionError("RESOURCE_METADATA_MISMATCH", ref["id"])
        else:
            key = (resource_type, ref["id"], ref["version"])
            entry = entries.get(key)
            if entry is None:
                raise ProjectionError("RESOURCE_REF_NOT_FOUND", str(key))
            if entry["identity"]["digest"] != ref["digest"]:
                raise ProjectionError("RESOURCE_DIGEST_MISMATCH", str(key))
        direct.append(entry)

    # Validate Model expression references against the same pinned catalog.
    model_ref = spec["model"]
    model_key = ("model", model_ref["id"], model_ref["version"])
    model_entry = entries[model_key]
    model_doc = model_documents.get(model_ref["id"])
    if model_doc is None:
        raise ProjectionError("MODEL_EXPRESSION_REF_MISMATCH", "model document unavailable")
    declared_exprs = []
    for equation in model_doc.get("equations", []):
        if "expressionRef" in equation:
            declared_exprs.append(equation["expressionRef"])
    for constraint in model_doc.get("constraints", []):
        if "expressionRef" in constraint:
            declared_exprs.append(constraint["expressionRef"])
    declared_exprs.extend(model_doc.get("validationCases", []))
    for ref in declared_exprs:
        key = ("expression", ref["id"], ref["version"])
        entry = entries.get(key)
        if entry is None or entry["identity"]["digest"] != ref["digest"]:
            raise ProjectionError("MODEL_EXPRESSION_REF_MISMATCH", str(key))
        # Ensure the catalog model dependency explicitly carries this expression.
        if not any(d["identity"] == entry["identity"] for d in model_entry["dependencies"]):
            raise ProjectionError("MODEL_EXPRESSION_REF_MISMATCH", "missing model-to-expression dependency")

    for entry in direct:
        rid = graph_id(entry["identity"])
        edges.add((root_id, rid, "requires"))
        queue.append(entry)

    visited = set()
    while queue:
        entry = queue.pop(0)
        ident = entry["identity"]
        key = identity_key(ident)
        if key in visited:
            continue
        visited.add(key)
        rid = graph_id(ident)
        node = {
            "resource_id": rid, "resource_type": ident["resource_type"],
            "version": ident["version"], "digest": ident["digest"],
            "storage": entry["storage"], "uri": entry["uri"]
        }
        if entry["storage"] == "restricted":
            node["access_policy_id"] = entry["access_policy_id"]
        previous = nodes.get(rid)
        if previous and previous != node:
            raise ProjectionError("DUPLICATE_CATALOG_IDENTITY", rid)
        nodes[rid] = node
        for dependency in entry["dependencies"]:
            dep_ident = dependency["identity"]
            dep_key = identity_key(dep_ident)
            dep_entry = entries.get(dep_key)
            if dep_entry is None:
                raise ProjectionError("TRANSITIVE_DEPENDENCY_MISSING", str(dep_key))
            if dep_entry["identity"]["digest"] != dep_ident["digest"]:
                raise ProjectionError("RESOURCE_DIGEST_MISMATCH", str(dep_key))
            dep_id = graph_id(dep_ident)
            edges.add((rid, dep_id, dependency["relation"]))
            queue.append(dep_entry)

    # Reachability, cycle detection and complete-closure check.
    adjacency = {rid: [] for rid in nodes}
    for src, dst, _ in edges:
        if src not in nodes or dst not in nodes:
            raise ProjectionError("TRANSITIVE_DEPENDENCY_MISSING", src + "->" + dst)
        adjacency[src].append(dst)
    colors = {}
    def visit(rid):
        if colors.get(rid) == 1:
            raise ProjectionError("DEPENDENCY_CYCLE", rid)
        if colors.get(rid) == 2:
            return
        colors[rid] = 1
        for child in adjacency[rid]:
            visit(child)
        colors[rid] = 2
    visit(root_id)
    reachable = set()
    stack = [root_id]
    while stack:
        rid = stack.pop()
        if rid not in reachable:
            reachable.add(rid)
            stack.extend(adjacency[rid])
    if reachable != set(nodes):
        raise ProjectionError("RESOURCE_OUTSIDE_CLOSURE", "unreachable node")

    graph = {
        "graph_version": "1alpha1", "root_resource_id": root_id,
        "policy": policy,
        "nodes": sorted(nodes.values(), key=lambda n: n["resource_id"].encode("utf-8")),
        "edges": [{"from": s, "to": d, "relation": r}
                  for s, d, r in sorted(edges, key=lambda x: (x[0].encode(), x[1].encode(), x[2].encode()))]
    }
    content = {
        "metadata": copy.deepcopy(manifest["metadata"]),
        "spec": copy.deepcopy(manifest["spec"])
    }
    resource_rows = []
    closure_rows = []
    for rid, node in nodes.items():
        if rid == root_id:
            continue
        entry = entries[(node["resource_type"], node["resource_id"].split(":", 1)[-1], node["version"])]
        resource_rows.append({
            "path": entry["path"], "resource_type": node["resource_type"],
            "resource_id": node["resource_id"].split(":", 1)[-1],
            "version": node["version"], "media_type": entry["media_type"],
            "size_bytes": entry["size_bytes"], "digest": node["digest"],
            "license_id": entry["license_id"]
        })
        closure_rows.append({
            "resource_type": node["resource_type"],
            "resource_id": node["resource_id"].split(":", 1)[-1],
            "version": node["version"], "digest": node["digest"]
        })
    projection = {
        "projection_version": "1alpha1",
        "package": {"api_version": manifest["apiVersion"], "package_id": package["id"],
                    "package_version": package["version"]},
        "content": content,
        "resources": sorted(resource_rows, key=lambda x: x["path"].encode("utf-8")),
        "dependency_closure": sorted(closure_rows, key=lambda x: (
            x["resource_type"].encode(), x["resource_id"].encode(),
            x["version"].encode(), x["digest"].encode()))
    }
    schema_validate(graph, GRAPH_SCHEMA, "RESOURCE_GRAPH_SCHEMA_INVALID")
    schema_validate(projection, PROJECTION_SCHEMA, "CANONICAL_PROJECTION_SCHEMA_INVALID")
    if manifest != original_manifest or catalog != original_catalog:
        raise ProjectionError("INPUT_MUTATED", "builder mutated an input")
    return graph, projection

def main():
    fixture = load(FIXTURE)
    manifest = fixture["manifest"]
    catalog = fixture["catalog"]
    model_docs = {manifest["spec"]["model"]["id"]: fixture["model_document"]}
    graph, projection = build_projection(manifest, catalog, fixture["source_manifest_digest"], model_docs)

    # Permutation invariance: catalog and dependency declaration order are not semantic.
    shuffled = copy.deepcopy(catalog)
    shuffled["resources"].reverse()
    for item in shuffled["resources"]:
        item["dependencies"].reverse()
    graph2, projection2 = build_projection(manifest, shuffled, fixture["source_manifest_digest"], model_docs)
    if graph != graph2 or projection != projection2:
        raise SystemExit("PERMUTATION_INVARIANCE_FAILED")

    def expect(code, mutate):
        m, c = copy.deepcopy(manifest), copy.deepcopy(catalog)
        mutate(m, c)
        try:
            build_projection(m, c, fixture["source_manifest_digest"], model_docs)
        except ProjectionError as exc:
            actual = exc.code
        else:
            actual = "ACCEPTED"
        if actual != code:
            raise SystemExit(f"expected {code}, got {actual}")

    expect("RESOURCE_REF_NOT_FOUND", lambda m, c: m["spec"]["scene"].update(id="missing"))
    expect("RESOURCE_DIGEST_MISMATCH", lambda m, c: m["spec"]["scene"].update(digest="sha256:"+"9"*64))
    expect("RESOURCE_METADATA_MISMATCH", lambda m, c: m["spec"]["assets"][0].update(licenseId="NOASSERTION"))
    expect("DUPLICATE_CATALOG_IDENTITY", lambda m, c: c["resources"].append(copy.deepcopy(c["resources"][0])))
    expect("TRANSITIVE_DEPENDENCY_MISSING", lambda m, c: c["resources"][0]["dependencies"][0]["identity"].update(resource_id="missing-expression"))
    expect("DEPENDENCY_CYCLE", lambda m, c: c["resources"][-1]["dependencies"].append({"identity":copy.deepcopy(c["resources"][0]["identity"]),"relation":"requires"}))
    expect("MODEL_EXPRESSION_REF_MISMATCH", lambda m, c: c["resources"][0]["dependencies"].clear())
    try:
        build_projection(manifest, catalog, None, model_docs)
    except ProjectionError as exc:
        if exc.code != "SOURCE_MANIFEST_DIGEST_REQUIRED":
            raise
    else:
        raise SystemExit("missing source digest was accepted")

    print("PASS: Manifest + Catalog projection reference builder; Graph/Projection schemas; transitive closure; Model Expression binding; permutation invariance; 8 rejection cases")
    print("REFERENCE VALIDATOR ONLY: no production package ingestion, content-byte verification, network, signature or license enforcement")

if __name__ == "__main__":
    main()
