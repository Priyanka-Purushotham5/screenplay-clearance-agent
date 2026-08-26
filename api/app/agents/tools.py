"""C4 — the Parallel search tool, as an ADK tool.

`web_search` is the only way any agent in this project reaches the open web.
It is a plain function with type hints and a docstring, which is what ADK
turns into a callable tool: the docstring below the signature is what the
model reads to decide how to call it.

Three properties matter more than anything else here.

**It never raises.** C5 researches one entity at a time, and a Parallel
outage during entity seven must mark entity seven and let entities eight
through twelve finish. An exception escaping this function would take the
whole run with it. Every failure path returns `{"status": "error", ...}`
with a machine-readable `code`, and the caller decides what that means.

**It returns snippets, not pages.** Measured against the A2 probe output —
three real searches, thirty results — raw excerpts run to a median of 1,827
characters and a maximum of 9,345, totalling 76.9k characters or roughly
19k tokens. C5 has a budget of six searches per entity. Unmanaged, that is
~38k tokens of payload for one entity, times twelve entities. `full_text`
exists for the case where a snippet genuinely is not enough, and it is off
by default.

**It strips page furniture before truncating.** This is not cosmetic. The
longest excerpt in the probe begins:

    tm logo  Services  Categories  Trademarks  Protect your brand today
    Register your Trademark  Post Filing Services …

Parallel returns page content, and page content often opens with
navigation. Taking the first 400 characters of that yields a snippet
containing no facts at all. Dropping the leading short unpunctuated lines
first, measured over the same thirty results, recovered the ATV Music
publishing credit on the Take On Me query — the actual answer to the actual
objective — at identical snippet length, and lost nothing on the other two
queries.

A relevance-scored selection was tried first and did not clearly beat plain
truncation: more compact, found one extra fact, lost another. At three
queries that is noise, so it is not here.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from api.app.config import settings

logger = logging.getLogger(__name__)

# `mode` trades cost and latency for depth. `basic` is ~1s and the SDK's
# recommended starting point; `advanced` costs more per search than the whole
# extraction stage costs per script.
DEFAULT_MODE = "basic"

# Per-snippet character cap. 400 keeps three searches near 2.4k tokens where
# uncapped they are 19k.
SNIPPET_CHARS = 400

# What `full_text=True` raises the cap to. Still a cap: the largest single
# excerpt observed was 9,345 characters, and one result should never be able
# to consume a research turn's whole context.
FULL_TEXT_CHARS = 4_000

# Asked of the API rather than trimmed here, so the payload never crosses the
# wire. 10 results at ~2.5k characters each is the observed shape.
MAX_CHARS_TOTAL = 30_000

REQUEST_TIMEOUT = 30.0
MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.5


def _clean(text: str) -> str:
    """Markdown to plain text. Removes ~19% outright, and more importantly
    stops link targets from eating the character budget: an excerpt full of
    `[text](https://very/long/url)` spends most of its length on hrefs that
    carry nothing for a rights question."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)      # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)   # links -> their text
    text = re.sub(r"https?://\S+", " ", text)              # bare urls
    text = re.sub(r"[|#*_>\\`]+", " ", text)               # table and heading furniture
    return text


def _drop_leading_furniture(text: str) -> str:
    """Skip leading lines that read as navigation rather than prose.

    A line qualifies as furniture when it is short and does not end like a
    sentence. Menu items ("Services", "Post Filing Services") match; real
    sentences and headings that end in a colon do not.

    Only the LEADING run is dropped. Furniture in the middle of a page is
    left alone, because the test is weak enough that applying it throughout
    would delete real content — table rows, credits, and short factual lines
    like "Published By - ATV Music Ltd." are exactly the shape this rule
    would otherwise discard.
    """
    lines = [line.strip() for line in text.split("\n")]
    start = 0
    while start < len(lines):
        line = lines[start]
        if not line or (len(line) < 45 and not line.endswith((".", "!", "?", ":"))):
            start += 1
            continue
        break
    return " ".join(line for line in lines[start:] if line)


def _snippet(excerpts: list[str], cap: int) -> str:
    joined = "\n".join(excerpts)
    body = _drop_leading_furniture(_clean(joined))
    body = re.sub(r"\s+", " ", body).strip()
    if len(body) <= cap:
        return body
    # Cut at a word boundary so the snippet does not end mid-token.
    cut = body[:cap].rsplit(" ", 1)[0]
    return cut + "…"


def _classify(exc: Exception) -> tuple[str, bool]:
    """Map an SDK exception to (code, retryable).

    Imported lazily so this module can be imported — and its pure functions
    tested — without `parallel-web` installed.
    """
    import parallel

    if isinstance(exc, parallel.APITimeoutError):
        return "TIMEOUT", True
    if isinstance(exc, parallel.RateLimitError):
        return "RATE_LIMITED", True
    if isinstance(exc, parallel.APIConnectionError):
        return "CONNECTION", True
    if isinstance(exc, parallel.InternalServerError):
        return "UPSTREAM_ERROR", True
    if isinstance(exc, parallel.AuthenticationError):
        return "AUTH", False
    if isinstance(exc, parallel.PermissionDeniedError):
        return "FORBIDDEN", False
    if isinstance(exc, (parallel.BadRequestError, parallel.UnprocessableEntityError)):
        return "BAD_REQUEST", False
    if isinstance(exc, parallel.APIStatusError):
        return "API_ERROR", False
    return "UNEXPECTED", False


def _error(code: str, detail: str, attempts: int, wall_ms: int) -> dict:
    logger.warning("web_search failed: %s — %s", code, detail)
    return {
        "status": "error",
        "code": code,
        "detail": detail,
        "results": [],
        "result_count": 0,
        "attempts": attempts,
        "wall_ms": wall_ms,
    }


def web_search(
    objective: str,
    search_queries: list[str],
    full_text: bool = False,
) -> dict:
    """Search the web for evidence about a rights question.

    Use this to find who owns or controls a work, mark, artwork, or name, and
    whether it is in the public domain. Pass several related queries in one
    call rather than calling repeatedly: the API bills one search unit per
    call regardless of how many queries it carries, so three queries in one
    call cost a third of three calls.

    Args:
        objective: What you are trying to establish, as a question. For
            example "Who owns the publishing rights to Take On Me by a-ha?".
            This steers which parts of each page come back.
        search_queries: Two to four short keyword queries covering different
            angles on the objective.
        full_text: Return longer extracts. Off by default. Turn it on only
            when a snippet is clearly truncating the answer, because long
            extracts crowd out later searches in the same research turn.

    Returns:
        On success: {"status": "ok", "results": [{"title", "url", "snippet",
        "publish_date"}], "result_count", "search_id", "attempts", "wall_ms"}.
        On failure: {"status": "error", "code", "detail", "results": []}.
        This never raises — check "status" before reading "results".
    """
    started = time.monotonic()

    if not settings.parallel_api_key:
        return _error(
            "NO_CREDENTIALS",
            "PARALLEL_API_KEY is not set. Add it to .env and restart the container.",
            0,
            0,
        )
    if not search_queries:
        return _error("BAD_REQUEST", "search_queries was empty.", 0, 0)

    import parallel

    client = parallel.Parallel(api_key=settings.parallel_api_key)
    cap = FULL_TEXT_CHARS if full_text else SNIPPET_CHARS

    last_code, last_detail = "UNEXPECTED", "no attempt was made"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.search(
                objective=objective,
                search_queries=list(search_queries),
                mode=DEFAULT_MODE,
                max_chars_total=MAX_CHARS_TOTAL,
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 — deliberate: nothing escapes
            last_code, retryable = _classify(exc)
            last_detail = f"{type(exc).__name__}: {exc}"
            if not retryable or attempt == MAX_ATTEMPTS:
                break
            # Exponential backoff. A rate limit answered with an immediate
            # retry is just a second rate limit.
            time.sleep(BACKOFF_BASE ** attempt)
            continue

        results = [
            {
                "title": r.title or "(untitled)",
                "url": r.url,
                "snippet": _snippet(list(r.excerpts or []), cap),
                "publish_date": r.publish_date,  # None on ~57% of results
            }
            for r in response.results
        ]
        wall_ms = int((time.monotonic() - started) * 1000)
        return {
            "status": "ok",
            "results": results,
            "result_count": len(results),
            "search_id": getattr(response, "search_id", None),
            "attempts": attempt,
            "wall_ms": wall_ms,
        }

    return _error(
        last_code,
        last_detail,
        MAX_ATTEMPTS if last_code in {"TIMEOUT", "RATE_LIMITED", "CONNECTION", "UPSTREAM_ERROR"} else 1,
        int((time.monotonic() - started) * 1000),
    )


def build_search_tool() -> Any:
    """The tool as ADK expects it, for `LlmAgent(tools=[...])`."""
    from google.adk.tools import FunctionTool

    return FunctionTool(func=web_search)
