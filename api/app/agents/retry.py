"""One retry policy, shared by every model call in the pipeline.

Why this is its own module
--------------------------
On 2026-09-03 a run finished, reported `complete`, and produced thirteen
findings with no red ones at all. Extraction had found twenty-three mentions
and research had completed; a single 503 from Gemini killed assessment batch
one, and batch one — in script order — held every mention that would have been
rated red. The failure was recorded honestly and the run still looked fine at a
glance.

Extraction had already been given backoff by then. Assessment had not, because
the retry policy lived inside extract.py as local constants and nothing carried
it across. Two copies of a policy is one copy and one omission, so it lives
here now and both import it.

What is retryable
-----------------
A 503 saying "spikes in demand are usually temporary, please try again later"
is worth waiting for. A 404 for a model that does not exist is not: it will
fail identically on every attempt, and spending twenty-four seconds confirming
that costs the one thing a demo cannot spare. The distinction is made on the
text of the exception because the Google client raises several unrelated
classes for transport failures and matching on type would miss some of them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Seconds before each attempt. The first is free. Retrying without backoff is
# not retrying, it is repeating — and repeating is what an overloaded model is
# asking you to stop doing.
RETRY_DELAYS: tuple[float, ...] = (0.0, 6.0, 18.0)

RETRYABLE: tuple[str, ...] = (
    "503", "500", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "INTERNAL",
    "DEADLINE_EXCEEDED", "Timeout", "timeout", "Connection", "overloaded",
)


# A 429 is two different failures wearing one status code, and the quotaId in
# the error body says which. `...PerMinutePerProjectPerModel...` is a rate
# limit: wait a few seconds and it clears. `...PerDayPerProject...` is the free
# tier's daily allowance — twenty requests for gemini-3.6-flash — and no amount
# of waiting inside one run will clear it.
#
# Treating them alike cost a real run: three assessment batches each retried
# three times against the daily wall, nine wasted calls and seventy-two seconds
# of backoff, and then the run reported zero findings.
DAILY_QUOTA = ("PerDayPerProject", "PerDayPerProjectPerModel")


def is_daily_quota(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(token in text for token in DAILY_QUOTA)


def is_retryable(exc: BaseException) -> bool:
    if is_daily_quota(exc):
        return False
    text = f"{type(exc).__name__}: {exc}"
    return any(token in text for token in RETRYABLE)


def describe(exc: BaseException) -> str:
    """A one-line version of an exception, for a warning a human will read.

    The Gemini client raises 429s carrying several hundred characters of JSON —
    quota metrics, help links, retry hints. Stored verbatim in `runs.stats` and
    joined into `runs.error`, that is what the user sees in the status bar. The
    useful sentence is always much shorter than the payload.
    """
    if is_daily_quota(exc):
        return ("Gemini free-tier daily quota exhausted (20 requests/day). "
                "It resets at midnight Pacific, or add billing to the API key.")
    text = " ".join(f"{exc}".split())
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        return "Gemini rate limit reached (429). Too many requests in a short window."
    if "503" in text or "UNAVAILABLE" in text:
        return "Gemini is temporarily unavailable (503). Usually a passing demand spike."
    return f"{type(exc).__name__}: {text[:160]}"


async def call_with_retries(
    fn: Callable[[], Awaitable[T]],
    *,
    label: str,
    delays: Sequence[float] = RETRY_DELAYS,
    on_error: Optional[Callable[[int, BaseException], None]] = None,
) -> T:
    """Call `fn`, retrying transient failures with backoff.

    Raises the last exception if every attempt fails, so the caller keeps
    whatever error handling it already had — this adds patience, it does not
    change the contract.

    `on_error` is called with (attempt, exception) after each failure, for a
    caller that wants to record every attempt rather than only the last.
    """
    last: BaseException | None = None

    for attempt in range(1, len(delays) + 1):
        delay = delays[attempt - 1]
        if delay:
            logger.info("waiting %.0fs before %s attempt %d", delay, label, attempt)
            await asyncio.sleep(delay)
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 — re-raised below if terminal
            last = exc
            if on_error is not None:
                on_error(attempt, exc)
            logger.warning("%s attempt %d failed: %s", label, attempt, describe(exc))
            if is_daily_quota(exc):
                logger.warning("%s: daily quota is spent; retrying today cannot "
                               "help, so stopping now", label)
                break
            if not is_retryable(exc):
                logger.warning("%s: %s is not retryable, giving up",
                               label, type(exc).__name__)
                break

    assert last is not None  # the loop only exits here via an exception
    raise last
