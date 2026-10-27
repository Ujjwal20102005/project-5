"""Factory pattern: create strategies by name; extensible via register()."""
from __future__ import annotations

from typing import Callable, Dict

from .strategies import (FastProcessingStrategy, IOBoundStrategy,
                         ProcessingStrategy, ThoroughProcessingStrategy)


class StrategyFactory:
    _registry: Dict[str, Callable[..., ProcessingStrategy]] = {
        "fast": FastProcessingStrategy,
        "io": IOBoundStrategy,
        "thorough": ThoroughProcessingStrategy,
    }

    @classmethod
    def register(cls, name: str, builder: Callable[..., ProcessingStrategy]) -> None:
        cls._registry[name] = builder

    @classmethod
    def available(cls):
        return sorted(cls._registry)

    @classmethod
    def create(cls, name: str, **kwargs) -> ProcessingStrategy:
        try:
            builder = cls._registry[name]
        except KeyError:
            raise ValueError(f"Unknown strategy '{name}'. Available: {cls.available()}") from None
        return builder(**kwargs)
