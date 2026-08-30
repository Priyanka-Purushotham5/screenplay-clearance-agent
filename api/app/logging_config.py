"""One place that makes the application's own logs visible.

Why this file exists
--------------------
Uvicorn configures three loggers — `uvicorn`, `uvicorn.error`, `uvicorn.access`
— and nothing else. The root logger keeps its default level (WARNING) with no
handlers attached, so Python falls back to `logging.lastResort`, which prints
WARNING and above and drops everything below it.

Every module here logs through `logging.getLogger(__name__)`, which inherits
from root. So `logger.info("run %s -> %s", ...)` in PostgresPersist.stage, and
every "research cache hit", "researched X in N searches" and "pipeline
complete" line, went nowhere. This was discovered the expensive way: a run hung
at `composing` and `docker compose logs api | grep "run .* ->"` returned
nothing at all — which looked like the code had not run, when in fact it had
run and the output had been thrown away.

That is worse than having no logging, because absence of a log line looked like
evidence and was not.

Calling this at import time in main.py fixes it for the API. Scripts under
api/scripts/ call it themselves.
"""

from __future__ import annotations

import logging
import os
import sys

# Libraries that log a line per HTTP request or per SQL statement. At INFO they
# bury the application's own output, which is the thing this file exists to
# make visible.
NOISY = {
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "urllib3": "WARNING",
    "asyncio": "WARNING",
    "sqlalchemy.engine": "WARNING",
    "google_genai": "WARNING",
    "google.adk": "WARNING",
    "google_genai.models": "WARNING",
}

_MARK = "_clearance_handler"


def configure_logging(level: str | None = None) -> None:
    """Attach one stdout handler to the root logger. Safe to call twice.

    Level comes from LOG_LEVEL, defaulting to INFO. Set LOG_LEVEL=DEBUG in
    .env when a run misbehaves and DEBUG=... lines are wanted; nothing needs
    rebuilding, only `docker compose up -d --force-recreate api`.
    """
    root = logging.getLogger()
    if any(getattr(handler, _MARK, False) for handler in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    ))
    setattr(handler, _MARK, True)
    root.addHandler(handler)
    root.setLevel((level or os.environ.get("LOG_LEVEL") or "INFO").upper())

    for name, noisy_level in NOISY.items():
        logging.getLogger(name).setLevel(noisy_level)

    # Uvicorn's own loggers have propagate=False, so raising the root level
    # does not duplicate its access log. Verified rather than assumed:
    # logging.getLogger("uvicorn.access").propagate is False.
