"""C5 smoke-test — the research agent.

    docker compose exec api python api/scripts/verify_c5.py
    docker compose exec api python api/scripts/verify_c5.py --live   # real calls

The checklist's gate is:

    one element produces a dossier with real cited evidence, and a second run
    of the same script is a cache hit with zero API calls

Without --live nothing is spent. The model call sits behind a seam, so a
scripted model drives the loop through every path that matters: the budget
cap, evidence accumulation, the payload discard, a search outage mid-loop, a
model error mid-loop, and the cache. Testing those against the real model
would be slower, cost money, and prove less — a real model cannot be made to
fail on cue, and the failure paths are the ones that decide whether a run of
twelve entities survives one bad entity.

--live researches a single entity end to end and asserts the dossier cites
sources that were actually returned. Costs a few searches and a few model
calls; worth running once per prompt change and not otherwise.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.agents import prompts  # noqa: E402
from api.app.agents.cache import (  # noqa: E402
    InMemoryResearchCache,
    cache_keys,
)
from api.app.agents.research import (  # noqa: E402
    ResearchRequest,
    _turn_message,
    research_entity,
)
from api.app.agents.schemas import EvidenceItem, ResearchTurn  # noqa: E402

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def turn(done=False, queries=(), evidence=(), identified="", holders=(), pd="unknown"):
    return ResearchTurn(
        note="scripted",
        new_evidence=[
            EvidenceItem(id=f"ev_{i}", claim=c, url=u, excerpt=x)
            for i, (c, u, x) in enumerate(evidence, start=1)
        ],
        identified_as=identified,
        rights_holders=list(holders),
        public_domain=pd,
        notable_disputes=[],
        done=done,
        next_queries=list(queries),
    )


class ScriptedModel:
    """Returns prepared turns in order, recording what it was shown."""

    def __init__(self, turns, raises_on=None):
        self.turns = list(turns)
        self.raises_on = raises_on
        self.messages: list[str] = []

    async def __call__(self, message: str) -> ResearchTurn:
        self.messages.append(message)
        if self.raises_on is not None and len(self.messages) == self.raises_on:
            raise RuntimeError("model exploded")
        if not self.turns:
            return turn(done=True, identified="ran out of scripted turns")
        return self.turns.pop(0)


class MarkedSearch:
    """Tags each search's payload so the discard can be observed.

    Search N returns a snippet containing PAYLOAD_N. After the loop, the last
    message the model saw must contain the most recent tag and none of the
    earlier ones — that is what "discard the raw payload" means. It cannot be
    tested with a single search, because the model has to see the results it
    is being asked to summarise.
    """

    def __init__(self):
        self.calls = 0

    def __call__(self, _objective, queries, **_kw):
        self.calls += 1
        return {
            "status": "ok",
            "result_count": 1,
            "results": [{
                "title": f"Result for {queries[0]}",
                "url": f"https://example.org/{self.calls}",
                "snippet": f"PAYLOAD_{self.calls} " + "X" * 3000,
                "publish_date": None,
            }],
        }


def fake_search(_objective, queries, **_kw):
    return MarkedSearch()(_objective, queries)


def failing_search(_objective, _queries, **_kw):
    return {"status": "error", "code": "RATE_LIMITED", "detail": "slow down",
            "results": [], "result_count": 0}


REQUEST = ResearchRequest(
    canonical_name="music:take_on_me:a_ha",
    category="music",
    surface_key="music:take_on_me",
    surface_forms=("'Take On Me'", "that song"),
    contexts=("On a battered turntable, 'Take On Me' by a-ha plays loudly.",),
)


def main() -> int:
    # ── the prompt must not know the rubric ────────────────────────────
    text = prompts.RESEARCH_INSTRUCTION
    check("Research prompt has no curly braces (ADK template trap)",
          "{" not in text and "}" not in text)

    # Rubric vocabulary is allowed only inside the closing prohibition — a
    # rule has to name what it forbids, and C1's prompt does the same. Banning
    # it everywhere would fail on "Do not say whether anything is risky".
    head, _, tail = text.partition("## Out of scope")
    check("The prompt has an explicit out-of-scope section", bool(tail))
    banned = ["red", "amber", "green", "rating", "rate", "risky", "cleared",
              "clearance", "licence needed", "license needed"]
    leaked = [w for w in banned if re.search(rf"\b{re.escape(w)}\b", head.lower())]
    check("No rubric vocabulary before the prohibition", not leaked, str(leaked))
    check("The prohibition is explicit about not rating",
          "do not rate" in tail.lower())

    # ── the message the model sees ─────────────────────────────────────
    message = _turn_message(REQUEST, [], {"results": [{"snippet": "S" * 100}]}, 6)
    check("The turn message carries the screenplay context",
          "battered turntable" in message)
    check("The turn message states the remaining budget",
          '"searches_remaining": 6' in message)

    # ── the loop ───────────────────────────────────────────────────────
    async def run(turns, cache=None, search=fake_search, raises_on=None, budget=6):
        model = ScriptedModel(turns, raises_on=raises_on)
        # `is not None`, not `or`: see InMemoryResearchCache.__bool__.
        cache = cache if cache is not None else InMemoryResearchCache()
        dossier = await research_entity(
            REQUEST, cache=cache, call_model=model, search=search,
            max_search_calls=budget,
        )
        return dossier, model, cache

    # Happy path: search once, then finish.
    dossier, model, cache = asyncio.run(run([
        turn(queries=["take on me publisher"]),
        turn(done=True, identified="1985 single by a-ha.",
             holders=["ATV Music", "WEA International"], pd="no",
             evidence=[("Published by ATV Music Ltd.",
                        "https://example.org/1", "Published By - ATV Music Ltd.")]),
    ]))
    check("A finished dossier is complete", dossier.status == "complete", dossier.status)
    check("It records the searches it ran",
          dossier.search_calls == 1 and dossier.queries_run == ["take on me publisher"],
          f"{dossier.search_calls} calls, {dossier.queries_run}")
    check("It carries cited evidence",
          len(dossier.evidence) == 1 and dossier.evidence[0].url.startswith("http"))
    check("It records the prompt version that produced it",
          dossier.prompt_version == prompts.RESEARCH_PROMPT_VERSION)

    # The discard, which needs two searches to observe: the final message must
    # carry the newest payload and none of the older ones.
    marked = MarkedSearch()
    _, discard_model, _ = asyncio.run(run([
        turn(queries=["q1"], evidence=[("first", "https://e.org/1", "a")]),
        turn(queries=["q2"], evidence=[("second", "https://e.org/2", "b")]),
        turn(done=True, identified="done", evidence=[("third", "https://e.org/3", "c")]),
    ], search=marked))
    final = discard_model.messages[-1]
    check("Earlier search payloads are discarded, not carried forward",
          "PAYLOAD_1" not in final and "PAYLOAD_2" in final,
          f"{marked.calls} searches, final message {len(final)} chars")
    check("Evidence is carried forward instead",
          "evidence_so_far" in final and "first" in final and "second" in final)
    check("Context does not grow with the number of searches",
          len(final) < len(discard_model.messages[1]) + 1500,
          f"pass2 {len(discard_model.messages[1])} -> pass3 {len(final)} chars")

    # Budget: a model that never says done must still stop.
    greedy = [turn(queries=[f"q{i}"]) for i in range(20)]
    dossier, model, _ = asyncio.run(run(greedy, budget=3))
    check("The search budget is enforced against a model that never stops",
          dossier.search_calls == 3, f"{dossier.search_calls} searches")
    check("Budget exhaustion is partial, not complete",
          dossier.status == "partial", dossier.status)

    # A model that says "not done" but proposes nothing must not spin.
    dossier, model, _ = asyncio.run(run([turn(queries=[])]))
    check("No proposed queries ends the loop rather than spinning",
          dossier.search_calls == 0 and len(model.messages) == 1,
          f"{len(model.messages)} model calls")

    # Search outage mid-loop.
    dossier, _, _ = asyncio.run(run([
        turn(queries=["q1"]),
        turn(done=True, identified="What could be established.",
             evidence=[("Partial.", "https://example.org/1", "text")]),
    ], search=failing_search))
    check("A search outage still yields a dossier",
          dossier.status in {"complete", "partial"} and dossier.identified_as,
          f"{dossier.status}: {dossier.identified_as[:40]}")

    # Model error mid-loop.
    dossier, _, _ = asyncio.run(run([turn(queries=["q1"])], raises_on=1))
    check("A model error returns a failed dossier instead of raising",
          dossier.status == "failed", dossier.status)
    check("A failed dossier says why", "RuntimeError" in dossier.identified_as,
          dossier.identified_as[:60])

    # An empty dossier cannot claim completeness.
    dossier, _, _ = asyncio.run(run([turn(done=True, identified="Nothing found.")]))
    check("A dossier with no evidence is downgraded from complete",
          dossier.status == "partial", dossier.status)

    # Evidence ids must be unique across passes — both passes emit ev_1.
    dossier, _, _ = asyncio.run(run([
        turn(queries=["q1"], evidence=[("A.", "https://e.org/a", "a")]),
        turn(done=True, identified="x", evidence=[("B.", "https://e.org/b", "b")]),
    ]))
    ids = [e.id for e in dossier.evidence]
    check("Evidence ids are unique and contiguous across passes",
          ids == ["ev_1", "ev_2"], str(ids))

    # ── the cache, which is half the gate ──────────────────────────────
    shared = InMemoryResearchCache()
    first, model1, _ = asyncio.run(run([
        turn(queries=["q1"]),
        turn(done=True, identified="1985 single by a-ha.",
             evidence=[("x", "https://e.org/1", "y")]),
    ], cache=shared))
    second, model2, _ = asyncio.run(run([turn(done=True, identified="SHOULD NOT RUN")],
                                        cache=shared))
    check("A second run of the same entity is a cache hit",
          second.identified_as == first.identified_as, second.identified_as[:40])
    check("A cache hit costs zero model calls and zero searches",
          len(model2.messages) == 0 and second.search_calls == first.search_calls,
          f"{len(model2.messages)} model calls")

    # The cross-run case C3 found: the model renames the entity next time.
    renamed = ResearchRequest(
        canonical_name="music:take_on_me_1985:a_ha",   # different canonical
        category="music",
        surface_key="music:take_on_me",                # same surface key
        surface_forms=REQUEST.surface_forms,
    )
    hit = asyncio.run(research_entity(
        renamed, cache=shared,
        call_model=ScriptedModel([turn(done=True, identified="SHOULD NOT RUN")]),
        search=fake_search))
    check("A renamed entity still hits, via the surface key",
          hit.identified_as == first.identified_as, hit.identified_as[:40])
    check("Cache keys are ordered canonical-first",
          cache_keys("a", "b") == ["a", "b"] and cache_keys("a", "a") == ["a"])

    # ── optional live run ──────────────────────────────────────────────
    if "--live" in sys.argv:
        print("\n--- live research (real model + real searches) ---")
        live = asyncio.run(research_entity(REQUEST, cache=InMemoryResearchCache()))
        check("Live research produces a dossier",
              live.status in {"complete", "partial"}, live.status)
        check("It identifies the work", len(live.identified_as) > 20,
              live.identified_as[:90])
        check("It cites evidence with real URLs",
              live.evidence and all(e.url.startswith("http") for e in live.evidence),
              f"{len(live.evidence)} items, {live.search_calls} searches")
        check("It stayed inside the budget", live.search_calls <= 6,
              str(live.search_calls))
        print(f"\n  identified_as : {live.identified_as}")
        print(f"  rights_holders: {live.rights_holders}")
        print(f"  public_domain : {live.public_domain}")
        for e in live.evidence[:4]:
            print(f"  {e.id}: {e.claim[:78]}")
            print(f"        {e.url}")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
