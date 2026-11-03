"""Reference verifier for short-lived tenant assertions.

This is a contract prototype, not a production issuer or PostgreSQL verifier.
The signing key must never be held by an untrusted client or ordinary handler.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


class TenantContextError(PermissionError):
    pass


@dataclass(frozen=True)
class VerifiedTenantContext:
    tenant_id: str
    subject: str
    audience: str
    action: str
    resource_id: str
    issued_at: int
    expires_at: int
    nonce: str


def _b64decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise TenantContextError("malformed tenant assertion") from exc


def verify_tenant_assertion(
    token: str,
    *,
    key: bytes,
    audience: str,
    action: str,
    resource_id: str,
    now: int | None = None,
    max_lifetime_seconds: int = 120,
) -> VerifiedTenantContext:
    """Verify a compact payload.signature HMAC assertion and exact request binding."""
    if not isinstance(key, bytes) or len(key) < 32:
        raise TenantContextError("verification key is invalid")
    if not isinstance(token, str) or len(token) > 8192 or token.count(".") != 1:
        raise TenantContextError("malformed tenant assertion")
    payload_part, signature_part = token.split(".")
    payload_bytes = _b64decode(payload_part)
    supplied = _b64decode(signature_part)
    expected = hmac.new(key, payload_part.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(supplied, expected):
        raise TenantContextError("tenant assertion signature invalid")
    try:
        payload = json.loads(payload_bytes)
    except Exception as exc:
        raise TenantContextError("tenant assertion payload invalid") from exc
    required = {"v", "tenant_id", "sub", "aud", "action", "resource_id",
                "iat", "exp", "nonce"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise TenantContextError("tenant assertion claims invalid")
    if payload["v"] != 1:
        raise TenantContextError("tenant assertion version unsupported")
    for field in ("tenant_id", "sub", "aud", "action", "resource_id", "nonce"):
        if not isinstance(payload[field], str) or not payload[field] or len(payload[field]) > 256:
            raise TenantContextError("tenant assertion claim invalid")
    if type(payload["iat"]) is not int or type(payload["exp"]) is not int:
        raise TenantContextError("tenant assertion time invalid")
    current = int(time.time()) if now is None else now
    if payload["iat"] > current or payload["exp"] <= current:
        raise TenantContextError("tenant assertion expired or not yet valid")
    if payload["exp"] <= payload["iat"] or payload["exp"] - payload["iat"] > max_lifetime_seconds:
        raise TenantContextError("tenant assertion lifetime invalid")
    if payload["aud"] != audience or payload["action"] != action or payload["resource_id"] != resource_id:
        raise TenantContextError("tenant assertion scope mismatch")
    return VerifiedTenantContext(
        tenant_id=payload["tenant_id"], subject=payload["sub"],
        audience=payload["aud"], action=payload["action"],
        resource_id=payload["resource_id"], issued_at=payload["iat"],
        expires_at=payload["exp"], nonce=payload["nonce"],
    )


def assert_job_tenant_binding(
    context: VerifiedTenantContext,
    *,
    persisted_tenant_id: str,
    job_id: str,
    payload_tenant_id: str | None = None,
) -> None:
    """Fail closed unless assertion, persisted Job row and optional payload agree."""
    if not persisted_tenant_id or not job_id:
        raise TenantContextError("persisted Job binding is missing")
    if context.tenant_id != persisted_tenant_id or context.resource_id != job_id:
        raise TenantContextError("assertion does not match persisted Job tenant/resource")
    if payload_tenant_id is not None and payload_tenant_id != persisted_tenant_id:
        raise TenantContextError("untrusted Job payload tenant mismatch")
