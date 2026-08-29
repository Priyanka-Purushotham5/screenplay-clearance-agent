"""Warm the research cache, deliberately and resumably.

    docker compose exec api python api/scripts/warm_cache.py --dry-run
    docker compose exec api python api/scripts/warm_cache.py --max 8
    docker compose exec api python api/scripts/warm_cache.py

Why this exists
---------------
`research_cache` is keyed on the entity, not the run or the script, and it
lives in Postgres. The first time anything researches `trademark:coca_cola`
it costs a few searches and a few model calls; every run afterwards — any
run, any script, forever — reads it for nothing.

That matters because of the budget. Measured on this project's key:

    limit: 20, model: gemini-2.5-flash
    quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier

Twenty requests per day. A cold run of the test screenplay is roughly one
extraction plus twelve entities at two or three passes each plus three
assessment batches — call it thirty to forty. You cannot finish one in a day.

A warm run is about four: extraction, and three batches of assessment. So
the difference between a demo you can rehearse and a demo you get one
attempt at is whether this script has been run.

Resumable, because it has to be
-------------------------------
Thirty calls against a twenty-call ceiling means the first attempt stops
partway. That is expected, not a failure. Entities already in the cache are
skipped for free, so tomorrow's run continues where today's stopped. Nothing
is lost and nothing is paid for twice.

It also stops on the FIRST quota refusal rather than grinding through the
remaining entities collecting identical errors — every one of those would be
a wasted round trip and a `failed` dossier written into the cache, which is
worse than no dossier at all, because a cached failure is a cached answer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from api.app.agents.cache import (  # noqa: E402
    PostgresResearchCache,
    cache_keys,
)
from api.app.agents.canonical import group_mentions  # noqa: E402
from api.app.agents.limiter import QuotaExhausted, RateLimiter  # noqa: E402
from api.app.agents.research import (  # noqa: E402
    ResearchRequest,
    _call_model_adk,
    research_entity,
)
from api.app.agents.tools import web_search  # noqa: E402
from api.app.config import settings  # noqa: E402

FIXTURES = ROOT / "api" / "app" / "agents" / "fixtures"
ELEMENTS = FIXTURES / "elements_fixture.json"
CHUNK = FIXTURES / "scene_fixture.json"


def load_entities():
    """The twelve entities of the frozen extraction, in the order C3 groups them."""
    elements = json.loads(ELEMENTS.read_text(encoding="utf-8"))["elements"]
    chunk = json.loads(CHUNK.read_text(encoding="utf-8"))
    text_of = {e["id"]: e["text"] for s in chunk["scenes"] for e in s["elements"]}
    grouped = group_mentions(elements)
    return grouped.groups, text_of


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what is cached and what is not. No calls.")
    parser.add_argument("--max", type=int, default=0,
                        help="Research at most N entities this session. "
                             "Use to stay inside a daily budget on purpose.")
    args = parser.parse_args()

    if not ELEMENTS.exists():
        print(f"No frozen extraction at {ELEMENTS.relative_to(ROOT)}.")
        print("Record one: python api/scripts/make_elements_fixture.py --freeze")
        return 2

    groups, text_of = load_entities()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # ── what is already there ──────────────────────────────────────────
    cached: list[str] = []
    todo = []
    async with Session() as session:
        cache = PostgresResearchCache(session)
        for group in groups:
            keys = cache_keys(group.canonical, group.surface_key)
            found = await cache.get(keys)
            if found is not None and found.status != "failed":
                cached.append(f"{group.canonical} ({found.status}, "
                              f"{len(found.evidence)} evidence)")
            else:
                # A cached failure is re-researched. It is an absence of an
                # answer wearing the shape of one, and leaving it in place
                # would make the gap permanent.
                todo.append(group)

    print(f"{len(groups)} entities in the frozen extraction")
    print(f"  {len(cached)} already cached")
    for line in cached:
        print(f"      {line}")
    print(f"  {len(todo)} to research")
    for group in todo:
        print(f"      {group.canonical} "
              f"({len(group.mentions)} mentions, {group.rubric_category})")

    if args.dry_run:
        print("\nDry run. Nothing called, nothing spent.")
        await engine.dispose()
        return 0
    if not todo:
        print("\nCache is warm. A run of this screenplay costs extraction "
              "plus assessment only.")
        await engine.dispose()
        return 0

    # ── research what is missing ───────────────────────────────────────
    limiter = RateLimiter()
    limited_model = limiter.wrap_gemini(_call_model_adk)
    limited_search = limiter.wrap_parallel(web_search)

    batch = todo[: args.max] if args.max else todo
    if len(batch) < len(todo):
        print(f"\nLimiting to {len(batch)} of {len(todo)} this session.")

    print(f"\nResearching {len(batch)} entities. {limiter.budget_report()}\n")
    done = failed = 0
    stopped_early = False

    for group in batch:
        request = ResearchRequest.from_group(group, text_of)
        # A session per entity, committed immediately: the whole point is that
        # entity seven surviving does not depend on entity eight.
        async with Session() as session:
            cache = PostgresResearchCache(session)
            try:
                dossier = await research_entity(
                    request, cache=cache,
                    call_model=limited_model, search=limited_search,
                )
            except QuotaExhausted as exc:
                print(f"  STOP  {group.canonical}: {exc}")
                stopped_early = True
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  ERR   {group.canonical}: {type(exc).__name__}: {exc}")
                failed += 1
                continue
            await session.commit()

        if dossier.status == "failed":
            # Almost always the daily cap reached mid-entity. Continuing would
            # write more failures into the cache, which is worse than stopping.
            print(f"  FAIL  {group.canonical}: {dossier.identified_as[:70]}")
            failed += 1
            stopped_early = True
            break

        done += 1
        print(f"  ok    {group.canonical}: {dossier.status}, "
              f"{len(dossier.evidence)} evidence, "
              f"{dossier.search_calls} searches")
        print(f"        {dossier.identified_as[:88]}")

    remaining = len(todo) - done
    print(f"\n{done} researched, {failed} failed, {remaining} still to do")
    print(limiter.budget_report())
    if stopped_early:
        print("\nStopped early. This is the expected shape on a free key: run "
              "it again tomorrow and it will skip everything already cached.")
    elif remaining == 0:
        print("\nCache is warm. A run of this screenplay now costs extraction "
              "plus assessment only.")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
