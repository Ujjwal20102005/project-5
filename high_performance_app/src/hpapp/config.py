"""Environment-driven configuration (12-factor style)."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Mapping, Optional


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8080
    db_path: str = "hpapp.db"
    cache_size: int = 10_000
    cache_ttl: float = 300.0
    workers: int = 32               # async worker tasks consuming the queue
    queue_size: int = 512           # bounded queue => back-pressure
    batch_size: int = 200           # DB write batch size
    strategy: str = "fast"          # fast | io | thorough
    process_workers: int = 0        # >0 => ProcessPool for CPU-bound strategy
    rate_limit_rps: float = 200.0
    rate_limit_burst: int = 400
    max_retries: int = 2
    breaker_threshold: int = 5
    breaker_recovery: float = 10.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        """Build settings from HPAPP_<FIELD> environment variables."""
        env = os.environ if env is None else env
        values = {}
        for f in fields(cls):
            raw = env.get(f"HPAPP_{f.name.upper()}")
            if raw is not None:
                values[f.name] = type(f.default)(raw)
        return cls(**values)
