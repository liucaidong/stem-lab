#!/usr/bin/env python3
"""Local fixture-only Package source/content integrity and catalog pinning checks."""
from __future__ import annotations
import base64, copy, hashlib, json, re, unicodedata
from pathlib import PurePosixPath
from pathlib import Path
import jsonschema, rfc8785

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "contracts/examples/package-content-integrity.fixtures.v1alpha1.json"
CATALOG_SCHEMA = ROOT / "contracts/package-resource-catalog-snapshot.schema.v1alpha2.json"
CATALOG_DOMAIN = b"stemlab-catalog-snapshot\x00"

class IntegrityError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)

def load_json_bytes(raw):
    def reject(value):
        raise ValueError("non-JSON numeric constant: " + value)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON property: " + key)
            result[key] = value
        return result
    return json.loads(raw, parse_constant=reject, object_pairs_hook=pairs)

def load_fixture():
    return load_json_bytes(FIXTURE.read_text(encoding="utf-8"))

def decode_bytes(encoded, code):
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise IntegrityError(code, "invalid base64 content") from exc

def sha256(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()

def validate_canonical_path(path):
    if (not isinstance(path, str) or not path or path.startswith("/")
            or "\\" in path or re.match(r"^[A-Za-z]:", path)
            or any(part in ("", ".", "..") for part in path.split("/"))
            or unicodedata.normalize("NFC", path) != path):
        raise IntegrityError("UNSAFE_RESOURCE_PATH", "canonical path rejected")
    return path

def catalog_projection(catalog):
    projected = copy.deepcopy(catalog)
    projected.pop("snapshot_digest", None)
    projected["resources"].sort(key=lambda item: tuple(
        item["identity"][field].encode("utf-8")
        for field in ("resource_type", "resource_id", "version", "digest")
    ))
    for resource in projected["resources"]:
        resource["dependencies"].sort(key=lambda item: (
            item["identity"]["resource_type"].encode("utf-8"),
            item["identity"]["resource_id"].encode("utf-8"),
            item["identity"]["version"].encode("utf-8"),
            item["identity"]["digest"].encode("utf-8"),
            item["relation"].encode("utf-8")
        ))
    projected["policy"]["external_host_allowlist"].sort(key=lambda value: value.encode("utf-8"))
    return projected

def catalog_digest(catalog):
    profile = catalog["snapshot_digest_profile"]
    if profile != "rfc8785-jcs-candidate-v1":
        raise IntegrityError("UNKNOWN_CATALOG_DIGEST_PROFILE", profile)
    payload = rfc8785.dumps(catalog_projection(catalog))
    return "sha256:" + hashlib.sha256(
        CATALOG_DOMAIN + profile.encode("ascii") + b"\x00" + payload
    ).hexdigest()

def validate_catalog(catalog):
    schema = load_json_bytes(CATALOG_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(catalog))
    if errors:
        raise IntegrityError("CATALOG_SCHEMA_INVALID", errors[0].message)
    identities = {}
    for resource in catalog["resources"]:
        ident = resource["identity"]
        key = tuple(ident[field] for field in ("resource_type", "resource_id", "version"))
        if key in identities:
            raise IntegrityError("DUPLICATE_CATALOG_IDENTITY", repr(key))
        identities[key] = ident["digest"]
        validate_canonical_path(resource["path"])
    for resource in catalog["resources"]:
        for dependency in resource["dependencies"]:
            ident = dependency["identity"]
            key = tuple(ident[field] for field in ("resource_type", "resource_id", "version"))
            if key not in identities or identities[key] != ident["digest"]:
                raise IntegrityError("CATALOG_DEPENDENCY_UNRESOLVED", repr(key))
    actual = catalog_digest(catalog)
    if actual != catalog["snapshot_digest"]:
        raise IntegrityError("CATALOG_SNAPSHOT_DIGEST_MISMATCH", actual)
    return actual

def validate_source_manifest(source):
    raw = decode_bytes(source["bytes_base64"], "SOURCE_MANIFEST_BASE64_INVALID")
    if len(raw) != source["size_bytes"]:
        raise IntegrityError("SOURCE_MANIFEST_SIZE_MISMATCH", str(len(raw)))
    actual = sha256(raw)
    if actual != source["digest"]:
        raise IntegrityError("SOURCE_MANIFEST_DIGEST_MISMATCH", actual)
    document = load_json_bytes(raw)
    metadata = document.get("metadata", {})
    if metadata.get("id") != source["package_id"] or metadata.get("version") != source["package_version"]:
        raise IntegrityError("SOURCE_MANIFEST_IDENTITY_MISMATCH", "manifest identity mismatch")
    return raw

def validate_resource_blobs(blobs):
    identities, paths = set(), set()
    for blob in blobs:
        identity = tuple(blob[field] for field in ("resource_type", "resource_id", "version"))
        if identity in identities:
            raise IntegrityError("DUPLICATE_RESOURCE_BLOB_IDENTITY", repr(identity))
        identities.add(identity)
        path = validate_canonical_path(blob["canonical_path"])
        if path in paths:
            raise IntegrityError("DUPLICATE_RESOURCE_BLOB_PATH", path)
        paths.add(path)
        raw = decode_bytes(blob["bytes_base64"], "RESOURCE_BLOB_BASE64_INVALID")
        if len(raw) != blob["size_bytes"]:
            raise IntegrityError("RESOURCE_BLOB_SIZE_MISMATCH", blob["resource_id"])
        if sha256(raw) != blob["digest"]:
            raise IntegrityError("RESOURCE_BLOB_DIGEST_MISMATCH", blob["resource_id"])
    return len(blobs)

def main():
    fixture = load_fixture()
    validate_source_manifest(fixture["source_manifest"])
    blob_count = validate_resource_blobs(fixture["resource_blobs"])
    snapshot_digest_value = validate_catalog(fixture["catalog_snapshot"])

    # Catalog record and dependency order are non-semantic.
    shuffled = copy.deepcopy(fixture["catalog_snapshot"])
    shuffled["resources"].reverse()
    for resource in shuffled["resources"]:
        resource["dependencies"].reverse()
    if catalog_digest(shuffled) != snapshot_digest_value:
        raise SystemExit("CATALOG_SNAPSHOT_ORDER_NOT_DETERMINISTIC")

    def expect(code, mutate):
        candidate = copy.deepcopy(fixture)
        mutate(candidate)
        try:
            if code.startswith("SOURCE_MANIFEST_"):
                validate_source_manifest(candidate["source_manifest"])
            elif code.startswith("RESOURCE_BLOB_") or code.startswith("UNSAFE_RESOURCE_PATH") or code.startswith("DUPLICATE_RESOURCE_BLOB_"):
                validate_resource_blobs(candidate["resource_blobs"])
            else:
                validate_catalog(candidate["catalog_snapshot"])
        except IntegrityError as exc:
            actual = exc.code
        else:
            actual = "ACCEPTED"
        if actual != code:
            raise SystemExit(f"expected {code}, got {actual}")

    expect("SOURCE_MANIFEST_DIGEST_MISMATCH", lambda f: f["source_manifest"].update(digest="sha256:"+"9"*64))
    expect("SOURCE_MANIFEST_SIZE_MISMATCH", lambda f: f["source_manifest"].update(size_bytes=1))
    expect("RESOURCE_BLOB_DIGEST_MISMATCH", lambda f: f["resource_blobs"][0].update(digest="sha256:"+"9"*64))
    expect("RESOURCE_BLOB_SIZE_MISMATCH", lambda f: f["resource_blobs"][0].update(size_bytes=1))
    expect("UNSAFE_RESOURCE_PATH", lambda f: f["resource_blobs"][0].update(canonical_path="../escape"))
    expect("DUPLICATE_RESOURCE_BLOB_IDENTITY", lambda f: f["resource_blobs"].append(copy.deepcopy(f["resource_blobs"][0])))
    expect("CATALOG_SNAPSHOT_DIGEST_MISMATCH", lambda f: f["catalog_snapshot"]["resources"][0].update(size_bytes=f["catalog_snapshot"]["resources"][0]["size_bytes"]+1))
    expect("DUPLICATE_CATALOG_IDENTITY", lambda f: f["catalog_snapshot"]["resources"].append(copy.deepcopy(f["catalog_snapshot"]["resources"][0])))

    print("PASS: exact source Manifest bytes/digest/identity; resource byte size/SHA-256; canonical path; pinned catalog snapshot JCS digest; order invariance; 8 rejection cases")
    print("FIXTURE-ONLY INTEGRITY HARNESS: no filesystem ingestion, object storage, network, production resolver or trust-root verification")

if __name__ == "__main__":
    main()
