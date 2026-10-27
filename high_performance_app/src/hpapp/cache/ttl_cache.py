"""Thread-safe LRU cache with TTL and statistics."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, maxsize: int = 1024, ttl: float = 300.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.maxsize, self.ttl, self._clock = maxsize, ttl, clock
        self._data: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = self.misses = self.evictions = self.expirations = 0

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return default
            expires_at, value = item
            if expires_at <= self._clock():
                del self._data[key]
                self.expirations += 1
                self.misses += 1
                return default
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        with self._lock:
            self._data[key] = (self._clock() + (self.ttl if ttl is None else ttl), value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)
                self.evictions += 1

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def stats(self) -> Dict[str, float]:
        total = self.hits + self.misses
        return {
            "size": len(self._data), "maxsize": self.maxsize, "hits": self.hits,
            "misses": self.misses, "evictions": self.evictions,
            "expirations": self.expirations,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }
