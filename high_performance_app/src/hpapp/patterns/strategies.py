"""Strategy pattern: interchangeable processing algorithms."""
from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from concurrent.futures import Executor
from typing import Any, Dict, Optional


def cpu_heavy(payload_json: str, rounds: int = 2000) -> str:
    """CPU-bound work (iterated hashing). Module-level so it is picklable."""
    h = payload_json.encode()
    for _ in range(rounds):
        h = hashlib.sha256(h).digest()
    return h.hex()


class ProcessingStrategy(ABC):
    name: str = "base"

    @abstractmethod
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process one payload and return a dict containing a 'digest'."""


def _canon(data: Dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


class FastProcessingStrategy(ProcessingStrategy):
    """Lightweight: a single SHA-256 digest, no I/O."""
    name = "fast"

    async def process(self, data):
        return {"status": "fast_processed",
                "digest": hashlib.sha256(_canon(data).encode()).hexdigest()}


class IOBoundStrategy(ProcessingStrategy):
    """Simulates an external call (HTTP/DB) with awaitable latency."""
    name = "io"

    def __init__(self, latency: float = 0.05):
        self.latency = latency

    async def process(self, data):
        await asyncio.sleep(self.latency)
        return {"status": "io_processed",
                "digest": hashlib.sha256(_canon(data).encode()).hexdigest()}


class ThoroughProcessingStrategy(ProcessingStrategy):
    """Heavy CPU work. Pass a ProcessPoolExecutor to escape the GIL."""
    name = "thorough"

    def __init__(self, executor: Optional[Executor] = None, rounds: int = 2000):
        self.executor = executor
        self.rounds = rounds

    async def process(self, data):
        loop = asyncio.get_running_loop()
        digest = await loop.run_in_executor(self.executor, cpu_heavy, _canon(data), self.rounds)
        return {"status": "thorough_processed", "digest": digest}
