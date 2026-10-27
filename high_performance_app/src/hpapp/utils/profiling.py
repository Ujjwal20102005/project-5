"""Profiling helpers: wall-clock timer and a cProfile context manager."""
from __future__ import annotations

import cProfile
import io
import pstats
import time
from contextlib import contextmanager


class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.perf_counter() - self.start
        return False


@contextmanager
def profile(top: int = 10, sort: str = "cumulative"):
    """Usage: `with profile() as p: work()` then `print(p.report)`."""
    class _Holder:
        report = ""
    holder = _Holder()
    prof = cProfile.Profile()
    prof.enable()
    try:
        yield holder
    finally:
        prof.disable()
        buf = io.StringIO()
        pstats.Stats(prof, stream=buf).sort_stats(sort).print_stats(top)
        holder.report = buf.getvalue()
