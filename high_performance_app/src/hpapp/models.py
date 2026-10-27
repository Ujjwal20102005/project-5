"""Plain data models shared across layers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Record:
    id: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def canonical(self) -> str:
        return json.dumps(self.payload, sort_keys=True, separators=(",", ":"), default=str)

    def cache_key(self, strategy_name: str) -> str:
        raw = f"{strategy_name}:{self.canonical()}".encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass
class Result:
    id: str
    status: str                      # "ok" | "failed"
    strategy: str
    digest: Optional[str] = None
    duration_ms: float = 0.0
    cached: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "status": self.status, "strategy": self.strategy,
            "digest": self.digest, "duration_ms": round(self.duration_ms, 3),
            "cached": self.cached, "error": self.error,
        }


@dataclass
class PipelineReport:
    total: int
    succeeded: int
    failed: int
    cached: int
    elapsed_s: float
    results: List[Result]

    @property
    def throughput(self) -> float:
        return self.total / self.elapsed_s if self.elapsed_s > 0 else 0.0

    def to_dict(self, include_results: bool = True) -> Dict[str, Any]:
        out = {
            "total": self.total, "succeeded": self.succeeded, "failed": self.failed,
            "cached": self.cached, "elapsed_s": round(self.elapsed_s, 4),
            "throughput_rps": round(self.throughput, 1),
        }
        if include_results:
            out["results"] = [r.to_dict() for r in self.results]
        return out
