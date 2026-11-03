"""R03.52.4 versionable error taxonomy and retry-policy reference."""
from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import Callable, Mapping
from runtime.worker_runtime import FailureDecision


@dataclass(frozen=True)
class RetryPolicy:
    error_code: str
    retryable: bool
    base_delay_seconds: float
    max_delay_seconds: float
    safe_message: str

    def __post_init__(self) -> None:
        if not self.error_code or len(self.error_code) > 128:
            raise ValueError("error_code must be 1..128 characters")
        if not self.safe_message or len(self.safe_message) > 512:
            raise ValueError("safe_message must be 1..512 characters")
        values = (self.base_delay_seconds, self.max_delay_seconds)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("retry delays must be finite and non-negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max delay cannot be lower than base delay")
        if not self.retryable and (self.base_delay_seconds or self.max_delay_seconds):
            raise ValueError("non-retryable policies must have zero delay bounds")


class RetryPolicyRegistry:
    """Maps stable error codes to safe retry decisions; raw exception text is ignored."""

    def __init__(self, policies: Mapping[str, RetryPolicy],
                 default_policy: RetryPolicy,
                 random_value: Callable[[], float] = random.random) -> None:
        if default_policy.retryable:
            raise ValueError("default policy must fail closed as non-retryable")
        if any(key != policy.error_code for key, policy in policies.items()):
            raise ValueError("policy mapping keys must match policy error_code")
        self._policies = dict(policies)
        self._default = default_policy
        self._random_value = random_value

    @classmethod
    def from_document(cls, document: Mapping[str, object],
                      random_value: Callable[[], float] = random.random) -> "RetryPolicyRegistry":
        def parse(raw: Mapping[str, object]) -> RetryPolicy:
            if not isinstance(raw.get("error_code"), str):
                raise ValueError("error_code must be a string")
            if type(raw.get("retryable")) is not bool:
                raise ValueError("retryable must be a boolean")
            if not isinstance(raw.get("safe_message"), str):
                raise ValueError("safe_message must be a string")
            for key in ("base_delay_seconds", "max_delay_seconds"):
                if type(raw.get(key)) not in (int, float):
                    raise ValueError(key + " must be numeric")
            return RetryPolicy(
                error_code=raw["error_code"],
                retryable=raw["retryable"],
                base_delay_seconds=float(raw["base_delay_seconds"]),
                max_delay_seconds=float(raw["max_delay_seconds"]),
                safe_message=raw["safe_message"],
            )
        default = parse(document["default_policy"])  # type: ignore[arg-type]
        policies = [parse(item) for item in document["policies"]]  # type: ignore[index]
        mapped = {policy.error_code: policy for policy in policies}
        if len(mapped) != len(policies):
            raise ValueError("duplicate error_code in retry policy registry")
        if default.error_code in mapped:
            raise ValueError("default error_code must not collide with an explicit policy")
        return cls(mapped, default, random_value)

    def decide(self, error_code: str, attempt_count: int,
               maximum_attempts: int) -> FailureDecision:
        if attempt_count < 1 or maximum_attempts < 1:
            raise ValueError("attempt_count and maximum_attempts must be positive")
        if attempt_count > maximum_attempts:
            raise ValueError("attempt_count cannot exceed maximum_attempts")
        policy = self._policies.get(error_code, self._default)
        if not policy.retryable or attempt_count >= maximum_attempts:
            return FailureDecision(False, policy.error_code, policy.safe_message, 0.0)
        ceiling = min(
            policy.max_delay_seconds,
            policy.base_delay_seconds * (2 ** (attempt_count - 1)),
        )
        sample = self._random_value()
        if not math.isfinite(sample) or sample < 0 or sample > 1:
            raise ValueError("random source must return a finite value in [0, 1]")
        return FailureDecision(True, policy.error_code, policy.safe_message, sample * ceiling)
