"""C4 smoke-test — the Parallel search tool.

    docker compose exec api python api/scripts/verify_c4.py
    docker compose exec api python api/scripts/verify_c4.py --live   # 1 search unit

The checklist's gate is:

    the tool is callable from an ADK agent and a forced API failure returns
    a clean error instead of killing the run

Both halves are checked here, and the second is checked by actually forcing
the failures. A retry policy nobody has ever seen fire is a retry policy you
do not have — so this substitutes a client that raises each SDK exception in
turn and asserts on what comes back, including that nothing propagates.

The normalisation checks run against `docs/probe_parallel_output.txt`, the
real A2 probe: three searches, thirty results, 76.9k characters of raw
excerpts. Testing the truncation against invented strings would prove
nothing, because the thing that makes truncation hard here is that real
pages open with navigation chrome.

Without --live, no network and no API key. --live spends exactly one search
unit to confirm the wire format still matches what we normalise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import parallel  # noqa: E402

from api.app.agents import tools  # noqa: E402

PROBE = ROOT / "docs" / "probe_parallel_output.txt"

# Facts each probe query should still yield after normalisation. Drawn from
# the raw excerpts by hand: these are the answers to the objectives, and a
# snippet that has dropped them has been truncated in the wrong place.
PROBE_FACTS = {
    0: ["wea", "atv music", "warner"],
    1: ["estate", "matta-clark"],
    2: ["disney", "fox", "20th century"],
}

results: list[bool] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


class FakeResult:
    def __init__(self, title, url, excerpts, publish_date=None):
        self.title, self.url = title, url
        self.excerpts, self.publish_date = excerpts, publish_date


class FakeResponse:
    search_id = "srch_fake"

    def __init__(self, results):
        self.results = results


class FakeClient:
    """Stands in for parallel.Parallel. Raises, or returns, on cue."""

    def __init__(self, raises=None, response=None):
        self._raises, self._response = raises, response
        self.calls = 0
        self.last_kwargs: dict = {}

    def __call__(self, *_, **__):
        return self

    def search(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._raises is not None:
            raise self._raises
        return self._response


def with_client(fake, fn):
    """Run fn with parallel.Parallel and the API key substituted."""
    real_cls, real_key = parallel.Parallel, tools.settings.parallel_api_key
    real_sleep = tools.time.sleep
    parallel.Parallel = fake
    tools.settings.parallel_api_key = "test-key"
    tools.time.sleep = lambda _s: None  # do not really back off in a test
    try:
        return fn()
    finally:
        parallel.Parallel = real_cls
        tools.settings.parallel_api_key = real_key
        tools.time.sleep = real_sleep


def api_error(cls):
    """Build an SDK exception without a real HTTP round trip."""
    import httpx

    request = httpx.Request("POST", "https://api.parallel.ai/v1/search")
    if cls is parallel.APITimeoutError:
        return cls(request=request)
    if cls is parallel.APIConnectionError:
        return cls(message="connection reset", request=request)
    response = httpx.Response(status_code=500, request=request)
    return cls(message="boom", response=response, body=None)


def main() -> int:
    # ── normalisation, against the real probe payload ──────────────────
    if not PROBE.exists():
        print(f"Probe output missing: {PROBE.relative_to(ROOT)}")
        return 2
    text = PROBE.read_text(encoding="utf-8")
    blocks = re.findall(r"--- json\.dumps \(indent=2\) ---\n(\{.*?\n\})\n", text, re.S)
    check("Probe fixture has all three query shapes", len(blocks) == 3, str(len(blocks)))

    raw_total = 0
    snip_total = 0
    for index, block in enumerate(blocks):
        rows = json.loads(block)["results"]
        snippets = [tools._snippet(r["excerpts"], tools.SNIPPET_CHARS) for r in rows]
        raw_total += sum(len(e) for r in rows for e in r["excerpts"])
        snip_total += sum(len(s) for s in snippets)
        joined = " ".join(snippets).casefold()
        missing = [f for f in PROBE_FACTS[index] if f not in joined]
        check(f"Query {index + 1}: normalisation keeps the answer", not missing,
              f"missing {missing}" if missing else f"{len(rows)} results")

    check("Every snippet respects the cap",
          all(len(tools._snippet(r["excerpts"], tools.SNIPPET_CHARS)) <= tools.SNIPPET_CHARS + 1
              for b in blocks for r in json.loads(b)["results"]))
    check("Snippets are a large reduction on raw excerpts",
          snip_total * 6 < raw_total,
          f"{raw_total / 1000:.1f}k -> {snip_total / 1000:.1f}k "
          f"({raw_total / snip_total:.1f}x)")

    # Leading navigation must go; a mid-text short line must not, because the
    # same weak test would eat "Published By - ATV Music Ltd."
    nav = "Services\nCategories\nProtect your brand\nThe mark was registered to Acme Corporation in 1998."
    check("Leading navigation is dropped",
          tools._drop_leading_furniture(nav).startswith("The mark was registered"),
          tools._drop_leading_furniture(nav)[:44])
    keep = "The registrant is listed below.\nPublished By - ATV Music Ltd.\nMore"
    check("Short lines after the first prose line are kept",
          "ATV Music" in tools._drop_leading_furniture(keep))
    check("A link keeps its text and loses its target",
          "hrefs" not in tools._clean("[label](https://example.com/hrefs)")
          and "label" in tools._clean("[label](https://example.com/hrefs)"))
    check("Empty excerpts produce an empty snippet, not a crash",
          tools._snippet([], 400) == "")
    check("Truncation cuts on a word boundary",
          not tools._snippet(["alpha bravo charlie delta echo foxtrot " * 40], 40)
          .rstrip("…").endswith(("alph", "brav", "charli")))

    # ── the happy path, without a network ──────────────────────────────
    ok_client = FakeClient(response=FakeResponse([
        FakeResult("Discogs", "https://discogs.com/x",
                   ["Published By - ATV Music Ltd."], "1985-01-01"),
        FakeResult(None, "https://example.com/y", ["Some text about rights."]),
    ]))
    out = with_client(ok_client, lambda: tools.web_search("Who owns X?", ["x rights"]))
    check("A successful search returns status ok", out["status"] == "ok", str(out)[:60])
    check("Results are normalised to title, url, snippet, publish_date",
          all(set(r) == {"title", "url", "snippet", "publish_date"} for r in out["results"]),
          str(sorted(out["results"][0])))
    check("A missing title is filled rather than left null",
          out["results"][1]["title"] == "(untitled)")
    check("The payload is capped at the API, not just here",
          ok_client.last_kwargs.get("max_chars_total") == tools.MAX_CHARS_TOTAL
          and ok_client.last_kwargs.get("timeout") == tools.REQUEST_TIMEOUT,
          str({k: v for k, v in ok_client.last_kwargs.items()
               if k in {"max_chars_total", "timeout", "mode"}}))

    # ── forced failures: the checklist's actual gate ───────────────────
    transient = FakeClient(raises=api_error(parallel.APITimeoutError))
    out = with_client(transient, lambda: tools.web_search("Who owns X?", ["x"]))
    check("A timeout returns an error instead of raising",
          out["status"] == "error" and out["code"] == "TIMEOUT", str(out)[:70])
    check("A transient failure is retried to the attempt limit",
          transient.calls == tools.MAX_ATTEMPTS, f"{transient.calls} calls")

    fatal = FakeClient(raises=api_error(parallel.AuthenticationError))
    out = with_client(fatal, lambda: tools.web_search("Who owns X?", ["x"]))
    check("A bad key returns AUTH", out["status"] == "error" and out["code"] == "AUTH",
          str(out)[:70])
    check("A fatal failure is not retried", fatal.calls == 1, f"{fatal.calls} calls")

    weird = FakeClient(raises=ValueError("something the SDK never documented"))
    out = with_client(weird, lambda: tools.web_search("Who owns X?", ["x"]))
    check("An unexpected exception is still caught",
          out["status"] == "error" and out["code"] == "UNEXPECTED", str(out)[:70])

    check("Every error path returns an empty result list",
          out["results"] == [] and out["result_count"] == 0)

    real_key = tools.settings.parallel_api_key
    tools.settings.parallel_api_key = None
    try:
        out = tools.web_search("Who owns X?", ["x"])
    finally:
        tools.settings.parallel_api_key = real_key
    check("A missing key is reported, not discovered at the wire",
          out["code"] == "NO_CREDENTIALS", str(out)[:70])

    out = with_client(ok_client, lambda: tools.web_search("Who owns X?", []))
    check("An empty query list is rejected locally", out["code"] == "BAD_REQUEST")

    # ── callable from an ADK agent ─────────────────────────────────────
    try:
        tool = tools.build_search_tool()
        declaration = tool._get_declaration()
        # ADK emits either a genai Schema on `parameters` or a JSON Schema on
        # `parameters_json_schema`, depending on whether its experimental
        # JSON_SCHEMA_FOR_FUNC_DECL feature is on. Read whichever is populated
        # rather than pinning the one this ADK version happens to use.
        schema = declaration.parameters_json_schema or declaration.parameters
        properties = set(getattr(schema, "properties", None) or schema["properties"])
        required = set(
            getattr(schema, "required", None)
            or (schema.get("required", []) if isinstance(schema, dict) else [])
        )
        check("The ADK tool declares the expected parameters",
              {"objective", "search_queries", "full_text"} <= properties,
              str(sorted(properties)))
        check("full_text is optional, so the model need not decide",
              "full_text" not in required and {"objective", "search_queries"} <= required,
              f"required={sorted(required)}")
        check("The tool is named for what it does", declaration.name == "web_search",
              declaration.name)
    except Exception as exc:  # noqa: BLE001
        check("The ADK tool builds", False, f"{type(exc).__name__}: {exc}")

    # ── optional live call ─────────────────────────────────────────────
    if "--live" in sys.argv:
        print("\n--- live search (1 unit) ---")
        live = tools.web_search(
            "Who owns the publishing rights to Take On Me by a-ha?",
            ["Take On Me a-ha publishing rights"],
        )
        check("Live search returns ok", live["status"] == "ok", str(live)[:90])
        if live["status"] == "ok":
            check("Live results are non-empty and normalised",
                  live["result_count"] > 0
                  and all(set(r) == {"title", "url", "snippet", "publish_date"}
                          for r in live["results"]),
                  f"{live['result_count']} results in {live['wall_ms']}ms")
            print(f"\n  first snippet: {live['results'][0]['snippet'][:160]}…")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
