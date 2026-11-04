"""Versioned retry policy registry; only the registry may choose retry behavior."""
from __future__ import annotations
import math
import random
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping
from runtime.worker_runtime import FailureDecision

MAX_RETRY_DELAY_MICROS = 86_400_000_000

@dataclass(frozen=True)
class RetryPolicy:
    error_code: str
    retryable: bool
    base_delay_micros: int
    max_delay_micros: int
    safe_message: str
    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.error_code):
            raise ValueError("error_code must be a stable uppercase code")
        if not self.safe_message or len(self.safe_message) > 512:
            raise ValueError("safe_message must be 1..512 characters")
        if type(self.base_delay_micros) is not int or type(self.max_delay_micros) is not int:
            raise ValueError("retry delays must be integer microseconds")
        if not 0 <= self.base_delay_micros <= MAX_RETRY_DELAY_MICROS or not 0 <= self.max_delay_micros <= MAX_RETRY_DELAY_MICROS:
            raise ValueError("retry delay outside [0, 24h]")
        if self.max_delay_micros < self.base_delay_micros:
            raise ValueError("max delay cannot be lower than base delay")
        if not self.retryable and (self.base_delay_micros or self.max_delay_micros):
            raise ValueError("non-retryable policies must have zero delay bounds")

class RetryPolicyRegistry:
    """Immutable, version-pinned mapping from stable error codes to safe decisions."""
    def __init__(self, policies: Mapping[str, RetryPolicy], default_policy: RetryPolicy,
                 policy_version: str, random_value: Callable[[], float] = random.random) -> None:
        if default_policy.retryable:
            raise ValueError("default policy must fail closed as non-retryable")
        if any(key != policy.error_code for key, policy in policies.items()):
            raise ValueError("policy mapping keys must match policy error_code")
        if not policy_version or len(policy_version) > 128:
            raise ValueError("policy_version must contain 1..128 characters")
        self._policies = MappingProxyType(dict(policies))
        self._default = default_policy
        self.policy_version = policy_version
        self._random_value = random_value

    @classmethod
    def from_document(cls, document: Mapping[str, object],
                      random_value: Callable[[], float] = random.random) -> "RetryPolicyRegistry":
        if document.get("schema_version") != "1alpha1":
            raise ValueError("unsupported retry policy schema_version")
        version = document.get("policy_version")
        if not isinstance(version, str) or not version:
            raise ValueError("policy_version is required")
        def parse(raw: Mapping[str, object]) -> RetryPolicy:
            if not isinstance(raw.get("error_code"), str):
                raise ValueError("error_code must be a string")
            if type(raw.get("retryable")) is not bool:
                raise ValueError("retryable must be a boolean")
            if not isinstance(raw.get("safe_message"), str):
                raise ValueError("safe_message must be a string")
            for key in ("base_delay_micros", "max_delay_micros"):
                if type(raw.get(key)) is not int:
                    raise ValueError(key + " must be an integer")
            return RetryPolicy(raw["error_code"], raw["retryable"],
                               raw["base_delay_micros"], raw["max_delay_micros"], raw["safe_message"])
        default = parse(document["default_policy"])  # type: ignore[arg-type]
        policies = [parse(item) for item in document["policies"]]  # type: ignore[index]
        mapped = {policy.error_code: policy for policy in policies}
        if len(mapped) != len(policies):
            raise ValueError("duplicate error_code in retry policy registry")
        if default.error_code in mapped:
            raise ValueError("default error_code must not collide with an explicit policy")
        return cls(mapped, default, version, random_value)

    def decide(self, error_code: str, attempt_count: int, maximum_attempts: int) -> FailureDecision:
        if type(attempt_count) is not int or type(maximum_attempts) is not int:
            raise ValueError("attempt counters must be integers")
        if attempt_count < 1 or maximum_attempts < 1 or maximum_attempts > 100 or attempt_count > maximum_attempts:
            raise ValueError("attempt_count and maximum_attempts must be within [1, 100]")
        if not isinstance(error_code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error_code):
            error_code = "__UNCLASSIFIED__"
        policy = self._policies.get(error_code, self._default)
        if not policy.retryable or attempt_count >= maximum_attempts:
            delay, retryable = 0, False
        else:
            ceiling = min(policy.max_delay_micros, policy.base_delay_micros * (2 ** (attempt_count - 1)))
            sample = self._random_value()
            if not math.isfinite(sample) or sample < 0 or sample > 1:
                raise ValueError("random source must return a finite value in [0, 1]")
            delay, retryable = int(sample * ceiling), True
        return FailureDecision(retryable, policy.error_code, policy.safe_message, delay, self.policy_version)
