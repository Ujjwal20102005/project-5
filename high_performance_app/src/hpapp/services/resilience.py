"""Resilience primitives: circuit breaker and token-bucket rate limiter."""
from __future__ import annotations

import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and calls are being short-circuited."""


class CircuitBreaker:
    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 10.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock
        self.state = self.CLOSED
        self.failures = 0
        self._opened_at = 0.0

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        if self.state == self.OPEN:
            if self._clock() - self._opened_at >= self.recovery_timeout:
                self.state = self.HALF_OPEN      # allow a single probe
            else:
                raise CircuitOpenError("circuit open")
        try:
            result = await func()
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    def _on_success(self) -> None:
        self.failures = 0
        self.state = self.CLOSED

    def _on_failure(self) -> None:
        self.failures += 1
        if self.state == self.HALF_OPEN or self.failures >= self.failure_threshold:
            self.state = self.OPEN
            self._opened_at = self._clock()


class TokenBucket:
    """Classic token bucket: `rate` tokens/second, burst up to `capacity`."""

    def __init__(self, rate: float, capacity: int,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.rate, self.capacity, self._clock = rate, float(capacity), clock
        self.tokens = float(capacity)
        self._last = clock()

    def allow(self, cost: float = 1.0) -> bool:
        now = self._clock()
        self.tokens = min(self.capacity, self.tokens + (now - self._last) * self.rate)
        self._last = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
