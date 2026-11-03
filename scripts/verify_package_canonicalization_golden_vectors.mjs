#!/usr/bin/env node
// Independent Node.js implementation for cross-language golden-vector checks.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const fixture = JSON.parse(readFileSync(
  new URL("../contracts/examples/package-canonicalization-golden-vectors.v1alpha1.json", import.meta.url),
  "utf8"
));
const domain = Buffer.from("stemlab-package-digest\0", "utf8");

function assertWellFormed(value) {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(i + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) throw new Error("unpaired high surrogate");
      i += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      throw new Error("unpaired low surrogate");
    }
  }
}

function jcs(value) {
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "string") {
    assertWellFormed(value);
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("non-finite number");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return "[" + value.map(jcs).join(",") + "]";
  if (typeof value === "object") {
    const keys = Object.keys(value).sort();
    return "{" + keys.map((key) => {
      assertWellFormed(key);
      return JSON.stringify(key) + ":" + jcs(value[key]);
    }).join(",") + "}";
  }
  throw new Error("unsupported JSON value");
}

function uint(major, number) {
  if (!Number.isSafeInteger(number) || number < 0) throw new Error("CBOR integer out of supported vector range");
  if (number < 24) return Buffer.from([(major << 5) | number]);
  if (number <= 0xff) return Buffer.from([(major << 5) | 24, number]);
  if (number <= 0xffff) {
    const out = Buffer.alloc(3); out[0] = (major << 5) | 25; out.writeUInt16BE(number, 1); return out;
  }
  if (number <= 0xffffffff) {
    const out = Buffer.alloc(5); out[0] = (major << 5) | 26; out.writeUInt32BE(number, 1); return out;
  }
  const out = Buffer.alloc(9); out[0] = (major << 5) | 27; out.writeBigUInt64BE(BigInt(number), 1); return out;
}

function cbor(value) {
  if (value === null) return Buffer.from([0xf6]);
  if (value === false) return Buffer.from([0xf4]);
  if (value === true) return Buffer.from([0xf5]);
  if (typeof value === "number" && Number.isSafeInteger(value)) {
    return value >= 0 ? uint(0, value) : uint(1, -1 - value);
  }
  if (typeof value === "string") {
    const bytes = Buffer.from(value, "utf8");
    return Buffer.concat([uint(3, bytes.length), bytes]);
  }
  if (Array.isArray(value)) return Buffer.concat([uint(4, value.length), ...value.map(cbor)]);
  if (typeof value === "object") {
    const pairs = Object.entries(value).map(([key, item]) => [cbor(key), cbor(item)]);
    pairs.sort((left, right) => left[0].length - right[0].length || Buffer.compare(left[0], right[0]));
    return Buffer.concat([uint(5, pairs.length), ...pairs.flat()]);
  }
  throw new Error("unsupported CBOR value");
}

let checked = 0;
for (const vector of fixture.vectors) {
  let bytes;
  if (vector.profile === "rfc8785-jcs") {
    const canonical = jcs(vector.input);
    assert.equal(canonical, vector.canonical_json, vector.id + ": canonical JSON");
    bytes = Buffer.from(canonical, "utf8");
  } else if (vector.profile === "cbor-rfc8949-core") {
    bytes = cbor(vector.input);
  } else {
    throw new Error("unknown profile " + vector.profile);
  }
  assert.equal(bytes.toString("hex"), vector.canonical_hex, vector.id + ": canonical bytes");
  const digest = "sha256:" + createHash("sha256")
    .update(Buffer.concat([domain, Buffer.from(vector.profile, "ascii"), Buffer.from([0]), bytes]))
    .digest("hex");
  assert.equal(digest, vector.digest, vector.id + ": digest");
  checked += 1;
}
console.log("PASS: independent Node.js golden vector verifier (" + checked + " vectors)");
console.log("LIMIT: CBOR verifier covers the current integer/text/map/array subset only; no production profile selected");
