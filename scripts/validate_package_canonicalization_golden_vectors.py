#!/usr/bin/env python3
"""Verify fixed JCS and Deterministic CBOR golden vectors with Python libraries."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import cbor2, rfc8785

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "contracts/examples/package-canonicalization-golden-vectors.v1alpha1.json"
DOMAIN = b"stemlab-package-digest\x00"

def load():
    def reject(value):
        raise ValueError("non-JSON numeric constant: " + value)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON property: " + key)
            result[key] = value
        return result
    return json.loads(FIXTURE.read_text(encoding="utf-8"),
                      parse_constant=reject, object_pairs_hook=pairs)

def main():
    document = load()
    if document.get("vector_set_version") != "1alpha1":
        raise SystemExit("unsupported golden vector set version")
    seen = set()
    for vector in document["vectors"]:
        key = (vector["profile"], vector["id"])
        if key in seen:
            raise SystemExit("duplicate golden vector: " + repr(key))
        seen.add(key)
        profile = vector["profile"]
        if profile == "rfc8785-jcs":
            actual = rfc8785.dumps(vector["input"])
            if actual != vector["canonical_json"].encode("utf-8"):
                raise SystemExit(f'{vector["id"]}: JCS canonical JSON mismatch')
        elif profile == "cbor-rfc8949-core":
            actual = cbor2.dumps(vector["input"], canonical=True)
        else:
            raise SystemExit("unknown profile: " + profile)
        if actual.hex() != vector["canonical_hex"]:
            raise SystemExit(f'{vector["id"]}: canonical bytes mismatch')
        digest = "sha256:" + hashlib.sha256(
            DOMAIN + profile.encode("ascii") + b"\x00" + actual
        ).hexdigest()
        if digest != vector["digest"]:
            raise SystemExit(f'{vector["id"]}: domain-separated digest mismatch')
    counts = {}
    for vector in document["vectors"]:
        counts[vector["profile"]] = counts.get(vector["profile"], 0) + 1
    print("PASS: Python golden vectors " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("GOLDEN VECTORS ONLY: JCS and CBOR remain candidates; DEC-27 remains OPEN")

if __name__ == "__main__":
    main()
