"""R03.52 adapter-neutral Worker Runtime reference core.

This module owns process-level orchestration only. Persistence, trusted tenant
context, broker transport, and production handler isolation remain adapters /
deployment concerns and are deliberately not selected here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Callable, Mapping, Protocol


@dataclass(frozen=True)
class ClaimedJob:
    tenant_id: str
    job_id: str
    job_type: str
    payload: Mapping[str, object]
    lease_owner: str
    lease_epoch: int
    attempt_count: int
    maximum_attempts: int
    lease_expires_at: str | None = None

    def __post_init__(self) -> None:
        if type(self.attempt_count) is not int or type(self.maximum_attempts) is not int:
            raise ValueError("attempt counters must be integers")
        if self.attempt_count < 1 or self.maximum_attempts < 1 or self.maximum_attempts > 100 or self.attempt_count > self.maximum_attempts:
            raise ValueError("attempt_count and maximum_attempts must be within [1, 100]")
        if type(self.lease_epoch) is not int or not 1 <= self.lease_epoch <= 9007199254740991:
            raise ValueError("lease_epoch must be a positive JSON-safe integer")


@dataclass(frozen=True)
class FailureDecision:
    retryable: bool
    error_code: str
    safe_message: str
    retry_delay_micros: int
    policy_version: str

    def __post_init__(self) -> None:
        if type(self.retryable) is not bool:
            raise ValueError("retryable must be boolean")
        import re
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.error_code):
            raise ValueError("error_code must be a stable uppercase code of at most 64 characters")
        if not self.safe_message or len(self.safe_message) > 512:
            raise ValueError("safe_message must contain 1..512 characters")
        if type(self.retry_delay_micros) is not int or not 0 <= self.retry_delay_micros <= 86400000000:
            raise ValueError("retry_delay_micros must be integer microseconds in [0, 24h]")
        if not self.retryable and self.retry_delay_micros != 0:
            raise ValueError("non-retryable decisions must have zero delay")
        if not self.policy_version or len(self.policy_version) > 128:
            raise ValueError("policy_version must be 1..128 characters")


@dataclass
class JobContext:
    """Signals a handler must observe before starting additional side effects."""
    shutdown_requested: Event = field(default_factory=Event)
    lease_lost: Event = field(default_factory=Event)

    def assert_lease(self) -> None:
        if self.lease_lost.is_set():
            raise LeaseLost("lease ownership was lost; stop work and do not commit")


class LeaseLost(RuntimeError):
    pass


class WorkerStore(Protocol):
    def claim(self, worker_id: str, lease_seconds: float) -> ClaimedJob | None: ...
    def renew(self, job: ClaimedJob, lease_seconds: float) -> bool: ...
    def complete(self, job: ClaimedJob, result: object) -> bool: ...
    def fail(self, job: ClaimedJob, decision: FailureDecision) -> bool: ...


class JobHandler(Protocol):
    def __call__(self, job: ClaimedJob, context: JobContext) -> object: ...


class RetryPolicyProvider(Protocol):
    def decide(self, error_code: str, attempt_count: int, maximum_attempts: int) -> FailureDecision: ...


class WorkerRuntime:
    """Single-slot, at-least-once worker loop with fail-closed lease heartbeat.

    A false/exceptional renewal marks the lease lost. The runtime then refuses
    completion/failure writes. Store methods must independently fence every
    mutation by tenant + job + owner + epoch + DB-clock expiry.
    """

    def __init__(
        self,
        *,
        worker_id: str,
        store: WorkerStore,
        handlers: Mapping[str, JobHandler],
        classify_error_code: Callable[[Exception], str],
        retry_policy: RetryPolicyProvider,
        lease_seconds: float = 30.0,
        heartbeat_interval_seconds: float = 10.0,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        from runtime.retry_policy import RetryPolicyRegistry
        if type(retry_policy) is not RetryPolicyRegistry:
            raise TypeError("WorkerRuntime requires the trusted RetryPolicyRegistry implementation")
        if not worker_id or lease_seconds <= 0 or heartbeat_interval_seconds <= 0:
            raise ValueError("worker_id and positive lease/heartbeat intervals are required")
        if heartbeat_interval_seconds >= lease_seconds:
            raise ValueError("heartbeat interval must be shorter than lease duration")
        if poll_interval_seconds < 0:
            raise ValueError("poll interval cannot be negative")
        self.worker_id = worker_id
        self.store = store
        self.handlers = dict(handlers)
        self.classify_error_code = classify_error_code
        self.retry_policy = retry_policy
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._shutdown = Event()

    def request_shutdown(self) -> None:
        """Stop claiming new work; an active handler is allowed to drain."""
        self._shutdown.set()

    def run_once(self) -> str:
        if self._shutdown.is_set():
            return "shutdown"
        job = self.store.claim(self.worker_id, self.lease_seconds)
        if job is None:
            return "idle"

        handler = self.handlers.get(job.job_type)
        if handler is None:
            decision = self.retry_policy.decide(
                "HANDLER_NOT_REGISTERED", job.attempt_count, job.maximum_attempts
            )
            if not self._shutdown.is_set():
                self.store.fail(job, decision)
            return "failed" if not self._shutdown.is_set() else "lease_unmodified"

        context = JobContext(shutdown_requested=self._shutdown)
        heartbeat_stop = Event()
        heartbeat = Thread(
            target=self._heartbeat_loop,
            args=(job, context, heartbeat_stop),
            name=f"lease-heartbeat-{job.job_id}",
            daemon=True,
        )
        heartbeat.start()
        outcome = "lease_unmodified"
        try:
            result = handler(job, context)
            context.assert_lease()
            heartbeat_stop.set()
            heartbeat.join()
            if context.lease_lost.is_set():
                return "lease_lost"
            return "succeeded" if self.store.complete(job, result) else "stale"
        except Exception as exc:
            heartbeat_stop.set()
            heartbeat.join()
            if context.lease_lost.is_set():
                return "lease_lost"
            try:
                error_code = self.classify_error_code(exc)
            except Exception:
                error_code = "__CLASSIFIER_FAILURE__"
            decision = self.retry_policy.decide(error_code, job.attempt_count, job.maximum_attempts)
            return "retry_or_dlq" if self.store.fail(job, decision) else "stale"
        finally:
            heartbeat_stop.set()
            heartbeat.join()

    def run_forever(self) -> None:
        """Poll until shutdown; no new claims occur after shutdown is requested."""
        while not self._shutdown.is_set():
            outcome = self.run_once()
            if outcome == "idle":
                self._shutdown.wait(self.poll_interval_seconds)

    def _heartbeat_loop(self, job: ClaimedJob, context: JobContext, stop: Event) -> None:
        while not stop.wait(self.heartbeat_interval_seconds):
            try:
                renewed = self.store.renew(job, self.lease_seconds)
            except Exception:
                renewed = False
            if not renewed:
                context.lease_lost.set()
                return
