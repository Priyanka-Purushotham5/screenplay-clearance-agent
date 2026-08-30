"""Research cache — keyed on the entity, shared across every script and run.

C5's gate is "a second run of the same script is a cache hit with zero API
calls". That is only achievable because research is per ENTITY: twelve
entities for a screenplay with thirty mentions, and the second run asks the
same twelve questions.

Why every dossier is stored under two keys
------------------------------------------
`research_cache` is keyed on `canonical_name`, and canonical names are
produced by a model. Measured across two extractions of the identical chunk,
eleven of twelve entities kept the same derived name and one did not:

    literary:hamlet_soliloquy            one run
    literary:to_be_or_not_to_be:hamlet   the next

Those are different structures, not different spellings, so no normalisation
rule connects them — and a cache keyed only on the canonical name would miss
that entity on every subsequent run, forever, while reporting a healthy hit
rate for the other eleven.

So a dossier is written under both its canonical name and its `surface_key`,
which C3 derives from the screenplay's own words and which was byte-identical
across those same two runs. Lookup tries the keys in order. The cost is one
extra row of a few kilobytes per entity; the alternative is a permanent miss
that nothing reports.

Storing the dossier twice rather than storing an alias row is deliberate. An
alias would need a `status` outside the complete/partial/failed vocabulary
and a second query to resolve, and cache rows are written once and never
updated, so the duplication cannot drift.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.agents.schemas import ResearchDossier
from api.app.models import ResearchCache as ResearchCacheRow

logger = logging.getLogger(__name__)


class ResearchCacheProtocol(Protocol):
    """What C5 needs. Two implementations: Postgres, and memory for tests."""

    async def get(self, keys: Sequence[str]) -> Optional[ResearchDossier]:
        ...

    async def put(self, dossier: ResearchDossier, keys: Sequence[str]) -> None:
        ...


class InMemoryResearchCache:
    """For tests and for running C5 without a database.

    Also counts hits and misses, because "zero API calls on the second run" is
    a claim that needs a number behind it.
    """

    def __init__(self) -> None:
        self._rows: dict[str, ResearchDossier] = {}
        self.hits = 0
        self.misses = 0

    async def get(self, keys: Sequence[str]) -> Optional[ResearchDossier]:
        for key in keys:
            found = self._rows.get(key)
            if found is not None:
                self.hits += 1
                return found
        self.misses += 1
        return None

    async def put(self, dossier: ResearchDossier, keys: Sequence[str]) -> None:
        for key in dict.fromkeys(k for k in keys if k):
            self._rows[key] = dossier

    def __len__(self) -> int:
        return len(self._rows)

    def __bool__(self) -> bool:
        """A cache is a cache whether or not it has anything in it.

        Without this, `__len__` makes an empty instance falsy, and the
        idiomatic `cache = cache or InMemoryResearchCache()` silently throws
        away a real cache on the one run where it matters most: the first.
        This cost four failing checks in verify_c5 before it was found.
        """
        return True


class PostgresResearchCache:
    """The real one. Takes a session rather than making its own, so a cache
    read and the run that follows it share a transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, keys: Sequence[str]) -> Optional[ResearchDossier]:
        wanted = [k for k in dict.fromkeys(keys) if k]
        if not wanted:
            return None

        rows = (
            await self._session.execute(
                select(ResearchCacheRow).where(
                    ResearchCacheRow.canonical_name.in_(wanted)
                )
            )
        ).scalars().all()
        if not rows:
            return None

        # Honour the caller's key order: the canonical name is the better key
        # and is passed first, so a surface-key row only wins when there is no
        # canonical row.
        by_key = {row.canonical_name: row for row in rows}
        for key in wanted:
            row = by_key.get(key)
            if row is None:
                continue
            try:
                return ResearchDossier.model_validate(row.dossier)
            except Exception as exc:  # noqa: BLE001
                # A row written by an older schema is a miss, not a crash.
                # Research costs a few searches; a failed run costs the demo.
                logger.warning("Unreadable cache row %s: %s", key, exc)
                return None
        return None

    async def put(self, dossier: ResearchDossier, keys: Sequence[str]) -> None:
        payload = dossier.model_dump(mode="json")
        for key in dict.fromkeys(k for k in keys if k):
            statement = pg_insert(ResearchCacheRow).values(
                canonical_name=key,
                category=dossier.category,
                dossier=payload,
                queries_run=dossier.queries_run,
                status=dossier.status,
            )
            # Upsert rather than insert. Two entities in one run can normalise
            # onto the same surface key, and a duplicate-key error at that
            # point would lose a dossier that has already been paid for.
            await self._session.execute(
                statement.on_conflict_do_update(
                    index_elements=[ResearchCacheRow.canonical_name],
                    set_={
                        "category": statement.excluded.category,
                        "dossier": statement.excluded.dossier,
                        "queries_run": statement.excluded.queries_run,
                        "status": statement.excluded.status,
                    },
                )
            )


class SessionPerCallResearchCache:
    """PostgresResearchCache, one session per operation.

    This is the one to use under C7's fan-out, and the plain
    `PostgresResearchCache` is the one to use from a script that owns its own
    session.

    Why the distinction is not cosmetic
    -----------------------------------
    `run_pipeline` researches up to six entities concurrently, and every one of
    them reads and writes this cache. `AsyncSession` is not concurrency-safe:
    two coroutines awaiting on one session is a bug, not a slow path. Measured
    directly, six concurrent reads through a single shared session give

        InvalidRequestError: This session is provisioning a new connection;
                             concurrent operations are not permitted

    and then leave the session in a state where even closing it raises
    `IllegalStateChangeError`. The first version of C8's `_execute` passed one
    shared session, which is what this class exists to make impossible.

    `warm_cache.py` already had the right shape — a session per entity,
    committed immediately — for the same reason: entity seven surviving must
    not depend on entity eight.

    It also counts hits and misses, which `PostgresResearchCache` does not.
    `run_pipeline` reads `cache.hits` with `getattr(cache, "hits", 0)`, so with
    the plain implementation a warm run truthfully reported zero cache hits in
    `runs.stats` — a statistic that was quietly always wrong.
    """

    def __init__(self, session_factory) -> None:
        self._sessions = session_factory
        self.hits = 0
        self.misses = 0

    async def get(self, keys: Sequence[str]) -> Optional[ResearchDossier]:
        async with self._sessions() as session:
            found = await PostgresResearchCache(session).get(keys)
        if found is None:
            self.misses += 1
        else:
            self.hits += 1
        return found

    async def put(self, dossier: ResearchDossier, keys: Sequence[str]) -> None:
        # Committed here rather than at the end of the run. A dossier is the
        # expensive artefact — six searches and a model call — and it should
        # survive a failure in a later entity, or in a later stage entirely.
        async with self._sessions() as session:
            await PostgresResearchCache(session).put(dossier, keys)
            await session.commit()

    def __bool__(self) -> bool:
        return True


def cache_keys(canonical_name: str, surface_key: str = "") -> list[str]:
    """The lookup order: canonical name first, surface key as the fallback."""
    return [k for k in dict.fromkeys([canonical_name, surface_key]) if k]
