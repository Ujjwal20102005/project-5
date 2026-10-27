"""Observer pattern: an async-friendly event bus."""
from __future__ import annotations

import inspect
import logging
from collections import defaultdict
from typing import Any, Callable, DefaultDict, List

log = logging.getLogger(__name__)

RECORD_PROCESSED = "record.processed"
RECORD_FAILED = "record.failed"
BATCH_COMPLETED = "batch.completed"

Callback = Callable[..., Any]


class EventBus:
    def __init__(self) -> None:
        self._subs: DefaultDict[str, List[Callback]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callback) -> None:
        self._subs[event].append(callback)

    def unsubscribe(self, event: str, callback: Callback) -> None:
        if callback in self._subs[event]:
            self._subs[event].remove(callback)

    async def publish(self, event: str, payload: Any = None) -> None:
        """Deliver to all subscribers; a failing subscriber never breaks the publisher."""
        for cb in list(self._subs.get(event, ())):
            try:
                out = cb(payload)
                if inspect.isawaitable(out):
                    await out
            except Exception:  # noqa: BLE001
                log.exception("subscriber failed for event %s", event)
