"""Observers that turn pipeline events into metrics."""
from __future__ import annotations

from ..patterns.observer import BATCH_COMPLETED, RECORD_FAILED, RECORD_PROCESSED, EventBus
from .metrics import Metrics


class MetricsObserver:
    def __init__(self, bus: EventBus, metrics: Metrics) -> None:
        self.metrics = metrics
        bus.subscribe(RECORD_PROCESSED, self.on_processed)
        bus.subscribe(RECORD_FAILED, self.on_failed)
        bus.subscribe(BATCH_COMPLETED, self.on_batch)

    def on_processed(self, result) -> None:
        self.metrics.inc("records_processed_total")
        if result.cached:
            self.metrics.inc("records_cached_total")
        self.metrics.observe("record_latency_ms", result.duration_ms)

    def on_failed(self, result) -> None:
        self.metrics.inc("records_failed_total")
        self.metrics.observe("record_latency_ms", result.duration_ms)

    def on_batch(self, info) -> None:
        self.metrics.inc("db_batches_total")
        self.metrics.inc("db_rows_written_total", info["rows"])
