"""R03.52.7.2 language-neutral Store / Unit-of-Work reference contract.

This module defines types and protocols only. It deliberately contains no
PostgreSQL driver, pool, migration runner, or production persistence adapter.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping, Protocol, Self


class StoreErrorCode(StrEnum):
    TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    LEASE_STALE = "LEASE_STALE"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    SESSION_REVISION_CONFLICT = "SESSION_REVISION_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    POOL_ACQUIRE_TIMEOUT = "POOL_ACQUIRE_TIMEOUT"
    TRANSIENT_DATABASE_FAILURE = "TRANSIENT_DATABASE_FAILURE"
    PERMANENT_DATABASE_FAILURE = "PERMANENT_DATABASE_FAILURE"
    TRANSACTION_OUTCOME_UNKNOWN = "TRANSACTION_OUTCOME_UNKNOWN"
    SCHEMA_VERSION_UNSUPPORTED = "SCHEMA_VERSION_UNSUPPORTED"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"


class StoreError(RuntimeError):
    """Stable error taxonomy; never expose raw SQL or driver exception text."""

    def __init__(
        self,
        code: StoreErrorCode,
        safe_message: str,
        *,
        retryable: bool = False,
        outcome_known: bool = True,
    ) -> None:
        if not safe_message or len(safe_message) > 512:
            raise ValueError("safe_message must contain 1..512 characters")
        if code is StoreErrorCode.TRANSACTION_OUTCOME_UNKNOWN and outcome_known:
            raise ValueError("unknown transaction outcome must set outcome_known=False")
        if outcome_known is False and code is not StoreErrorCode.TRANSACTION_OUTCOME_UNKNOWN:
            raise ValueError("only TRANSACTION_OUTCOME_UNKNOWN may have unknown outcome")
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        self.outcome_known = outcome_known
        super().__init__(f"{code.value}: {safe_message}")


@dataclass(frozen=True)
class StoreAccessContext:
    """Opaque signed access assertion; tenant identity is not caller input."""

    assertion: str
    audience: str

    def __post_init__(self) -> None:
        if not self.assertion or len(self.assertion) > 8192:
            raise ValueError("assertion must contain 1..8192 characters")
        if not self.audience or len(self.audience) > 256:
            raise ValueError("audience must contain 1..256 characters")


@dataclass(frozen=True)
class ClaimRequest:
    worker_id: str
    supported_job_types: tuple[str, ...]
    lease_seconds: float
    max_items: int = 1

    def __post_init__(self) -> None:
        if not self.worker_id or len(self.worker_id) > 128:
            raise ValueError("worker_id must contain 1..128 characters")
        if not self.supported_job_types or len(self.supported_job_types) > 64:
            raise ValueError("supported_job_types must contain 1..64 entries")
        if any(not item or len(item) > 128 for item in self.supported_job_types):
            raise ValueError("job types must contain 1..128 characters")
        if len(set(self.supported_job_types)) != len(self.supported_job_types):
            raise ValueError("supported_job_types must be unique")
        if not 1.0 <= self.lease_seconds <= 300.0:
            raise ValueError("lease_seconds must be between 1 and 300")
        # The current WorkerRuntime is single-slot per poller. Batching is a
        # future capability and must not be inferred from a driver API.
        if self.max_items != 1:
            raise ValueError("max_items is fixed at 1 in v1alpha1")


@dataclass(frozen=True)
class JobLease:
    tenant_id: str
    job_id: str
    owner: str
    epoch: int
    expires_at: datetime

    def __post_init__(self) -> None:
        for name, value in (
            ("tenant_id", self.tenant_id),
            ("job_id", self.job_id),
            ("owner", self.owner),
        ):
            if not value or len(value) > 256:
                raise ValueError(f"{name} must contain 1..256 characters")
        if self.epoch < 1:
            raise ValueError("lease epoch must be >= 1")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("lease expiry must be timezone-aware")


@dataclass(frozen=True)
class ClaimedJobRecord:
    lease: JobLease
    job_type: str
    payload: Mapping[str, object]
    attempt_count: int
    maximum_attempts: int

    def __post_init__(self) -> None:
        if not self.job_type or len(self.job_type) > 128:
            raise ValueError("job_type must contain 1..128 characters")
        if type(self.attempt_count) is not int or type(self.maximum_attempts) is not int:
            raise ValueError("attempt counters must be integers")
        if self.attempt_count < 1 or self.maximum_attempts < 1 or self.attempt_count > self.maximum_attempts:
            raise ValueError("attempt_count must be in [1, maximum_attempts]")
        payload_tenant = self.payload.get("tenant_id")
        if payload_tenant is not None and payload_tenant != self.lease.tenant_id:
            raise ValueError("payload tenant_id must match persisted Job tenant")


@dataclass(frozen=True)
class CompleteJobCommand:
    lease: JobLease
    expected_session_revision: int
    result_ref: str
    idempotency_key: str
    request_digest: str

    def __post_init__(self) -> None:
        if self.expected_session_revision < 0:
            raise ValueError("expected_session_revision must be >= 0")
        if not self.result_ref or len(self.result_ref) > 1024:
            raise ValueError("result_ref must contain 1..1024 characters")
        if not self.idempotency_key or len(self.idempotency_key) > 256:
            raise ValueError("idempotency_key must contain 1..256 characters")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.request_digest):
            raise ValueError("request_digest must be a lowercase sha256 digest")


@dataclass(frozen=True)
class FailJobCommand:
    lease: JobLease
    error_code: str
    safe_message: str
    retryable: bool
    retry_delay_micros: int
    retry_policy_version: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", self.error_code):
            raise ValueError("error_code must be a stable uppercase code")
        if not self.safe_message or len(self.safe_message) > 512:
            raise ValueError("safe_message must contain 1..512 characters")
        if type(self.retry_delay_micros) is not int or not 0 <= self.retry_delay_micros <= 86400000000:
            raise ValueError("retry_delay_micros must be integer microseconds in [0, 24h]")
        if not self.retry_policy_version or len(self.retry_policy_version) > 128:
            raise ValueError("retry_policy_version must contain 1..128 characters")
        if not self.retryable and self.retry_delay_micros != 0:
            raise ValueError("non-retryable failures must have zero delay")
        if not self.idempotency_key or len(self.idempotency_key) > 256:
            raise ValueError("idempotency_key must contain 1..256 characters")


class StoreOutcome(StrEnum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    DEAD_LETTERED = "DEAD_LETTERED"


class UnitOfWork(Protocol):
    """One tenant-bound DB transaction; single-use and never spans a handler."""

    def claim(self, request: ClaimRequest) -> ClaimedJobRecord | None: ...
    def renew(self, lease: JobLease, lease_seconds: float) -> StoreOutcome: ...
    def complete(self, command: CompleteJobCommand) -> StoreOutcome: ...
    def fail(self, command: FailJobCommand) -> StoreOutcome: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...


class Store(Protocol):
    """Driver-neutral persistence boundary; adapters own acquisition and reset."""

    def begin(
        self,
        access_context: StoreAccessContext,
        *,
        timeout_seconds: float,
    ) -> UnitOfWork: ...


class WorkerStoreFacade(Protocol):
    """Short-transaction facade consumed by WorkerRuntime."""

    def claim(self, worker_id: str, lease_seconds: float) -> object | None: ...
    def renew(self, job: object, lease_seconds: float) -> bool: ...
    def complete(self, job: object, result: object) -> bool: ...
    def fail(self, job: object, decision: object) -> bool: ...
