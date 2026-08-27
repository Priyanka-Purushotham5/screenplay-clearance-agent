"""Shared rate limiting across every external call the pipeline makes.

One limiter per run, shared by Gemini and Parallel. Not one per stage: the
quota is per project, so two stages each politely staying under the limit
still breach it together. Research and assessment both call Gemini, and on a
free key they are competing for the same twenty requests.

Why this matters more than it looks
-----------------------------------
Measured on the project's own key:

    429 RESOURCE_EXHAUSTED ... limit: 20, model: gemini-2.5-flash
    quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier

Twenty requests per DAY. A full script is twelve entities at two or three
model calls each plus assessment batches — thirty to forty calls. Without
pacing, a run does not fail cleanly at the end; it degrades in the middle,
and the C6 live run that produced this module is the proof: the Coca-Cola
dossier came back `failed, 0 evidence` while the ratings around it looked
fine. A clean-looking score from a half-researched run is the worst outcome
available, because nothing about it looks wrong.

Two mechanisms
--------------
**A token bucket** paces requests per minute and smooths bursts. Refills
continuously rather than resetting on a boundary, so twenty calls at 12:00:59
do not become forty across a minute boundary.

**A daily budget**, which a bucket cannot express. When it is spent, calls
fail fast with a structured error instead of waiting on a limit that will not
lift for hours. Failing fast is the kindness here: the alternative is a run
that appears to hang.

Every limit is an environment variable, because the right numbers depend on
whether the key is free or billed and that changes without warning.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class QuotaExhausted(RuntimeError):
    """The daily budget is spent. Distinct from a 429, which will pass."""


class TokenBucket:
    """Classic token bucket, async.

    `rate_per_minute` tokens accrue continuously; `burst` is the ceiling. A
    burst equal to the rate lets a run start at full speed and then settle,
    which suits a pipeline that fans out and then goes quiet.
    """

    def __init__(self, rate_per_minute: float, burst: Optional[float] = None) -> None:
        self.rate = max(rate_per_minute, 0.001) / 60.0     # tokens per second
        self.capacity = float(burst if burst is not None else rate_per_minute)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()
        self.waited_seconds = 0.0

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(
                    self.capacity, self._tokens + (now - self._updated) * self.rate
                )
                self._updated = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                delay = (tokens - self._tokens) / self.rate
                self.waited_seconds += delay
                # Held under the lock on purpose: releasing it would let a
                # second caller through while this one sleeps, which is how a
                # bucket quietly becomes no bucket at all under fan-out.
                await asyncio.sleep(delay)


@dataclass
class LimiterStats:
    gemini_calls: int = 0
    parallel_calls: int = 0
    gemini_denied: int = 0
    parallel_denied: int = 0
    waited_seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "gemini_calls": self.gemini_calls,
            "parallel_calls": self.parallel_calls,
            "gemini_denied": self.gemini_denied,
            "parallel_denied": self.parallel_denied,
            "waited_seconds": round(self.waited_seconds, 2),
        }


@dataclass
class RateLimiter:
    """One per run. Wrap a call and it is paced and counted."""

    gemini_rpm: int = field(default_factory=lambda: _int_env("GEMINI_RPM", 10))
    gemini_daily: int = field(default_factory=lambda: _int_env("GEMINI_DAILY", 20))
    parallel_rpm: int = field(default_factory=lambda: _int_env("PARALLEL_RPM", 30))
    parallel_daily: int = field(default_factory=lambda: _int_env("PARALLEL_DAILY", 500))

    def __post_init__(self) -> None:
        self._gemini = TokenBucket(self.gemini_rpm)
        self._parallel = TokenBucket(self.parallel_rpm)
        self.gemini_remaining = self.gemini_daily
        self.parallel_remaining = self.parallel_daily
        self.stats = LimiterStats()

    # ── budgets ────────────────────────────────────────────────────────
    def _spend(self, which: str) -> None:
        if which == "gemini":
            if self.gemini_remaining <= 0:
                self.stats.gemini_denied += 1
                raise QuotaExhausted(
                    f"Gemini daily budget of {self.gemini_daily} is spent. "
                    "Raise GEMINI_DAILY if the key is billed, or wait for the "
                    "quota to reset."
                )
            self.gemini_remaining -= 1
            self.stats.gemini_calls += 1
        else:
            if self.parallel_remaining <= 0:
                self.stats.parallel_denied += 1
                raise QuotaExhausted(
                    f"Parallel daily budget of {self.parallel_daily} is spent."
                )
            self.parallel_remaining -= 1
            self.stats.parallel_calls += 1

    def _sync_wait(self) -> None:
        self.stats.waited_seconds = round(
            self._gemini.waited_seconds + self._parallel.waited_seconds, 2
        )

    # ── wrappers ───────────────────────────────────────────────────────
    def wrap_gemini(
        self, fn: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        async def limited(*args, **kwargs) -> T:
            self._spend("gemini")
            await self._gemini.acquire()
            self._sync_wait()
            return await fn(*args, **kwargs)

        return limited

    def wrap_parallel(self, fn: Callable[..., dict]) -> Callable[..., dict]:
        """Parallel's tool is sync, so this is too.

        It also never raises, matching `web_search`'s contract: a spent budget
        comes back as a structured error the research loop already knows how
        to record, rather than an exception that would take the run down.
        """

        def limited(*args, **kwargs) -> dict:
            try:
                self._spend("parallel")
            except QuotaExhausted as exc:
                return {"status": "error", "code": "QUOTA_EXHAUSTED",
                        "detail": str(exc), "results": [], "result_count": 0}
            # Sync bucket wait. Parallel calls happen inside a worker slot, so
            # blocking here paces that slot rather than the event loop.
            deadline = time.monotonic()
            self._parallel._tokens -= 1
            if self._parallel._tokens < 0:
                delay = (-self._parallel._tokens) / self._parallel.rate
                self._parallel.waited_seconds += delay
                time.sleep(delay)
                self._parallel._tokens = 0
            self._parallel._updated = deadline
            self._sync_wait()
            return fn(*args, **kwargs)

        return limited

    def budget_report(self) -> str:
        return (f"gemini {self.gemini_remaining}/{self.gemini_daily} left, "
                f"parallel {self.parallel_remaining}/{self.parallel_daily} left")
