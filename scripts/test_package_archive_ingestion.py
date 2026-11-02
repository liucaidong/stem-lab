#!/usr/bin/env python3
"""In-memory ZIP ingestion gate; never extracts files to disk."""
from __future__ import annotations
import copy, hashlib, io, json, stat, struct, warnings, zipfile
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
POLICY_SCHEMA = ROOT / "contracts/package-ingestion-policy.schema.v1alpha1.json"
POLICY_FIXTURE = ROOT / "contracts/examples/package-archive-ingestion.fixtures.v1alpha1.json"
CONTENT_FIXTURE = ROOT / "contracts/examples/package-content-integrity.fixtures.v1alpha1.json"

class ArchiveError(Exception):
    def __init__(self, code, message=""):
        self.code = code
        super().__init__(message or code)

def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON property: " + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)

def sha256(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()

def expected_files(content_fixture):
    source = content_fixture["source_manifest"]
    files = {
        "manifest.json": {
            "bytes": __import__("base64").b64decode(source["bytes_base64"], validate=True),
            "digest": source["digest"],
            "size_bytes": source["size_bytes"]
        }
    }
    for item in content_fixture["resource_blobs"]:
        files[item["canonical_path"]] = {
            "bytes": __import__("base64").b64decode(item["bytes_base64"], validate=True),
            "digest": item["digest"],
            "size_bytes": item["size_bytes"]
        }
    return files

def validate_archive(archive_bytes, policy, expected):
    if len(archive_bytes) > policy["max_archive_bytes"]:
        raise ArchiveError("ARCHIVE_TOO_LARGE")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError("INVALID_ARCHIVE", str(exc)) from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > policy["max_entries"]:
            raise ArchiveError("ENTRY_COUNT_EXCEEDED")
        names, folded = set(), set()
        total = 0
        for info in infos:
            name = info.filename
            if (not name or name.startswith("/") or "\\" in name
                    or any(part in ("", ".", "..") for part in name.split("/"))
                    or (len(name) >= 2 and name[1] == ":")):
                raise ArchiveError("UNSAFE_ARCHIVE_PATH", name)
            if name in names:
                raise ArchiveError("DUPLICATE_ARCHIVE_PATH", name)
            names.add(name)
            folded_name = name.casefold()
            if not policy["allow_casefold_collisions"] and folded_name in folded:
                raise ArchiveError("ARCHIVE_PATH_CASE_COLLISION", name)
            folded.add(folded_name)
            if info.is_dir():
                raise ArchiveError("DIRECTORY_ENTRY_NOT_ALLOWED", name)
            mode = (info.external_attr >> 16) & 0o170000
            if policy["reject_symlinks"] and mode == stat.S_IFLNK:
                raise ArchiveError("SYMLINK_ENTRY_REJECTED", name)
            if policy["reject_encrypted"] and (info.flag_bits & 0x1):
                raise ArchiveError("ENCRYPTED_ENTRY_REJECTED", name)
            method_names = {
                zipfile.ZIP_STORED: "stored",
                zipfile.ZIP_DEFLATED: "deflated",
            }
            method = method_names.get(info.compress_type)
            if method is None or method not in policy["allowed_compression_methods"]:
                raise ArchiveError("UNSUPPORTED_COMPRESSION", name)
            if info.file_size > policy["max_entry_bytes"]:
                raise ArchiveError("ENTRY_SIZE_EXCEEDED", name)
            total += info.file_size
            if total > policy["max_total_uncompressed_bytes"]:
                raise ArchiveError("TOTAL_UNCOMPRESSED_SIZE_EXCEEDED")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > policy["max_compression_ratio"]:
                raise ArchiveError("COMPRESSION_RATIO_EXCEEDED", name)

        if policy["require_manifest_at_root"] and "manifest.json" not in names:
            raise ArchiveError("MANIFEST_MISSING")
        missing = set(expected) - names
        if missing:
            raise ArchiveError("EXPECTED_ENTRY_MISSING", sorted(missing)[0])
        undeclared = names - set(expected)
        if undeclared:
            raise ArchiveError("UNDECLARED_ENTRY", sorted(undeclared)[0])

        for info in infos:
            with archive.open(info, "r") as stream:
                payload = stream.read(policy["max_entry_bytes"] + 1)
            if len(payload) > policy["max_entry_bytes"]:
                raise ArchiveError("ENTRY_SIZE_EXCEEDED", info.filename)
            expected_item = expected[info.filename]
            if len(payload) != expected_item["size_bytes"]:
                raise ArchiveError("RESOURCE_SIZE_MISMATCH", info.filename)
            if sha256(payload) != expected_item["digest"]:
                raise ArchiveError("RESOURCE_DIGEST_MISMATCH", info.filename)
            if payload != expected_item["bytes"]:
                raise ArchiveError("RESOURCE_BYTES_MISMATCH", info.filename)
    return len(infos)

def build_archive(files, compression=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(output, "w", compression=compression) as archive:
            for name, payload in files:
                archive.writestr(name, payload)
    return output.getvalue()

def mark_encrypted(archive_bytes):
    data = bytearray(archive_bytes)
    offset = 0
    while True:
        local = data.find(b"PK\x03\x04", offset)
        central = data.find(b"PK\x01\x02", offset)
        candidates = [x for x in (local, central) if x >= 0]
        if not candidates:
            break
        pos = min(candidates)
        flag_offset = pos + (6 if data[pos:pos+4] == b"PK\x03\x04" else 8)
        flags = struct.unpack_from("<H", data, flag_offset)[0]
        struct.pack_into("<H", data, flag_offset, flags | 0x1)
        offset = pos + 4
    return bytes(data)

def main():
    policy_fixture = load(POLICY_FIXTURE)
    policy = policy_fixture["policy"]
    schema = load(POLICY_SCHEMA)
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(policy))
    if errors:
        raise SystemExit("ingestion policy schema invalid: " + errors[0].message)
    content = load(CONTENT_FIXTURE)
    expected = expected_files(content)
    files = [(name, item["bytes"]) for name, item in expected.items()]
    valid_archive = build_archive(files)
    count = validate_archive(valid_archive, policy, expected)
    if count != len(expected):
        raise SystemExit("valid archive entry count mismatch")

    def expect(code, archive, expected_override=None, policy_override=None):
        try:
            validate_archive(archive, policy_override or policy, expected_override or expected)
        except ArchiveError as exc:
            actual = exc.code
        else:
            actual = "ACCEPTED"
        if actual != code:
            raise SystemExit(f"expected {code}, got {actual}")

    expect("UNSAFE_ARCHIVE_PATH", build_archive(files + [("../escape", b"x")]))
    expect("UNSAFE_ARCHIVE_PATH", build_archive(files + [("/absolute", b"x")]))
    expect("UNSAFE_ARCHIVE_PATH", build_archive(files + [("bad\\path", b"x")]))
    expect("DUPLICATE_ARCHIVE_PATH", build_archive(files + [("manifest.json", expected["manifest.json"]["bytes"])]))
    expect("ARCHIVE_PATH_CASE_COLLISION", build_archive(files + [("ASSETS/DIAGRAM.SVG", b"x")]))
    symlink_info = zipfile.ZipInfo("linked-resource")
    symlink_info.create_system = 3
    symlink_info.external_attr = (stat.S_IFLNK | 0o777) << 16
    symlink_archive = io.BytesIO()
    with zipfile.ZipFile(symlink_archive, "w") as zf:
        zf.writestr(symlink_info, b"manifest.json")
    expect("SYMLINK_ENTRY_REJECTED", symlink_archive.getvalue())
    expect("ENCRYPTED_ENTRY_REJECTED", mark_encrypted(valid_archive))
    ratio_archive = build_archive([("manifest.json", b"A" * 8192)])
    expect("COMPRESSION_RATIO_EXCEEDED", ratio_archive, {"manifest.json": {"bytes": b"A"*8192, "size_bytes":8192, "digest":sha256(b"A"*8192)}})
    too_many_policy = copy.deepcopy(policy)
    too_many_policy["max_entries"] = 1
    expect("ENTRY_COUNT_EXCEEDED", valid_archive, policy_override=too_many_policy)
    too_large_policy = copy.deepcopy(policy)
    too_large_policy["max_entry_bytes"] = 10
    expect("ENTRY_SIZE_EXCEEDED", valid_archive, policy_override=too_large_policy)
    expect("MANIFEST_MISSING", build_archive([(k,v["bytes"]) for k,v in expected.items() if k!="manifest.json"]))
    expect("UNDECLARED_ENTRY", build_archive(files + [("extra.txt", b"extra")]))
    wrong_digest = copy.deepcopy(expected)
    wrong_digest["models/dc-model.json"]["digest"] = "sha256:" + "9"*64
    expect("RESOURCE_DIGEST_MISMATCH", valid_archive, wrong_digest)
    bzip_archive = build_archive(files, compression=zipfile.ZIP_BZIP2)
    expect("UNSUPPORTED_COMPRESSION", bzip_archive)

    print("PASS: in-memory archive validation; path traversal; duplicates/casefold; symlink/encryption; compression ratio/method; count/size limits; manifest and resource binding; 13 rejection cases")
    print("NO EXTRACTION: archive entries are streamed from memory; no filesystem writes, network, object storage or production quarantine service")

if __name__ == "__main__":
    main()
