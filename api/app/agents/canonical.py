"""C3 — canonicalisation and dedup.

Extraction returns one record per MENTION. Research is expensive and belongs
to the ENTITY. This module is the join between those two shapes.

    30 mentions  ->  N entities  ->  N research dossiers  ->  30 findings

The rule that governs everything here: **grouping is for research only.**
Every mention keeps its own category, element type, surface form and rating.
`music:take_on_me` heard in an action line is RED and named in dialogue is
GREEN — that difference is the product, and no amount of deduplication may
blur it. Groups exist so the same facts are not looked up five times.

Why this is harder than lowercasing
-----------------------------------
The canonical name is a model opinion, not data, and it moves. Observed
across three runs of an identical chunk:

    music:take_on_me:a-ha   and   music:a_ha        in the same response
    literary:hamlet_soliloquy     one run
    literary:to_be_or_not_to_be:hamlet   the next

and one company arriving under five names at once:

    logo:coca_cola  trademark:coca_cola  product:coca_cola_bottle
    product:coca_cola_drink  other:coca_cola_polar_bear

Normalising punctuation fixes the first line and nothing else — measured, it
moved 19 names to 19. What actually collapses the fragmentation is matching
on the SLUG, because the slug is the part the model is most consistent about
and the category is the part it is least consistent about. The same
Coca-Cola line came back `trademark` on one run and `product` on the next.

Two merge passes, both conservative
-----------------------------------
1. Slug-core. `coca_cola_bottle` folds into `coca_cola` because the shorter
   slug is a complete TOKEN prefix of the longer. Token-wise, so `nobu` never
   swallows `nobuko`.

2. Qualifier link. `music:a_ha` folds into `music:take_on_me:a_ha` because
   `a_ha` is the qualifier of the other name — the artist of that work — AND
   the two names occur on the same script element. That co-occurrence is
   evidence from the document rather than a guess, and without it the rule
   would happily merge an unrelated person who shared a surname with a
   painter.

Category routing
----------------
C6's rubric has criteria for music, trademark, artwork, person, location,
clip and literary. Extraction emits `product`, `logo` and `other` as well —
five of thirty mentions on the observed run, including the disparaged
Coca-Cola line, which is the hardest case in the test screenplay. Those
mentions would reach C6 and be rated by nothing at all, silently.

So each group carries a `rubric_category`: the most common routable category
among its own mentions, falling back to an explicit alias for the
unroutable ones. The mention keeps its raw category, because "logo facing
the lens" genuinely is more prominent than a bottle on a table and that
distinction is worth preserving all the way to the rating.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# C6's per-category criteria. A mention whose category is outside this set has
# no rubric rule and would receive no rating.
RUBRIC_CATEGORIES = frozenset(
    {"music", "trademark", "artwork", "person", "location", "clip", "literary"}
)

# Where the unroutable categories go when a group has no routable category of
# its own. `logo` and `product` are both depictions of a mark; `character_name`
# is the screenplay's own cast and is not a clearance item at all.
CATEGORY_ALIASES = {
    "logo": "trademark",
    "product": "trademark",
    "character_name": "person",
}


@dataclass(frozen=True)
class ParsedName:
    """A canonical name split into its declared parts.

    The contract from C1's prompt is `{category}:{slug}[:{qualifier}]`.
    Anything that does not fit is kept whole in `slug` rather than dropped,
    so a malformed name still groups with its own duplicates.
    """

    category: str
    slug: str
    qualifier: Optional[str]

    @property
    def normal(self) -> str:
        parts = [self.category, self.slug] + ([self.qualifier] if self.qualifier else [])
        return ":".join(parts)

    @property
    def tokens(self) -> tuple[str, ...]:
        return tuple(t for t in self.slug.split("_") if t)


@dataclass
class EntityGroup:
    """One real-world thing, and every mention of it in this chunk."""

    canonical: str
    rubric_category: str
    mentions: list[dict] = field(default_factory=list)
    # Every raw canonical_name folded into this group, including the winner.
    # Kept so a merge can be audited rather than taken on trust.
    aliases: set[str] = field(default_factory=set)

    @property
    def element_types(self) -> tuple[str, ...]:
        return tuple(sorted({m["element_type"] for m in self.mentions}))

    @property
    def surface_key(self) -> str:
        """A second cache key, derived from the script rather than the model.

        Grouping stabilises the canonical name for most entities, but not
        all: across two runs the Hamlet quote came back as
        `literary:hamlet_soliloquy` and then `literary:to_be_or_not_to_be:
        hamlet`. Those are different *structures*, and no normalisation rule
        turns one into the other.

        The surface form has no such problem, because it is copied out of the
        screenplay. `research_cache` persists between runs, so C5 should try
        the canonical name first and fall back to this — otherwise an entity
        the model renames is a permanent cache miss, and "a second run is a
        cache hit with zero API calls" quietly stops being true.

        Most common surface form wins, ties broken alphabetically so the key
        does not depend on mention order.
        """
        counts = Counter(m["surface_form"] for m in self.mentions)
        top = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        return f"{self.rubric_category}:{normalise_part(top)}"

    @property
    def element_ids(self) -> frozenset[str]:
        return frozenset(m["script_element_id"] for m in self.mentions)


@dataclass
class GroupResult:
    groups: list[EntityGroup]
    warnings: list[str] = field(default_factory=list)

    @property
    def mention_count(self) -> int:
        return sum(len(g.mentions) for g in self.groups)

    @property
    def reduction(self) -> float:
        return self.mention_count / len(self.groups) if self.groups else 0.0


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalise_part(part: str) -> str:
    """Lowercase, and collapse every run of non-alphanumerics to one underscore.

    `a-ha` and `a_ha` and `A-Ha` all land on `a_ha`. This is the cheap half of
    the problem and it is worth doing exactly because it is cheap — but on the
    observed data it merged nothing on its own.
    """
    return re.sub(r"[^a-z0-9]+", "_", part.strip().casefold()).strip("_")


def parse_name(canonical_name: str) -> ParsedName:
    parts = [normalise_part(p) for p in canonical_name.split(":")]
    parts = [p for p in parts if p]

    if not parts:
        return ParsedName(category="other", slug="unknown", qualifier=None)
    if len(parts) == 1:
        # No category prefix. Keep the whole thing as the slug rather than
        # inventing a category we would then group on.
        return ParsedName(category="other", slug=parts[0], qualifier=None)
    if len(parts) == 2:
        return ParsedName(category=parts[0], slug=parts[1], qualifier=None)
    # Three or more: extra colons join into the qualifier rather than being
    # discarded, so `a:b:c:d` keeps `c_d` instead of silently losing `d`.
    return ParsedName(category=parts[0], slug=parts[1], qualifier="_".join(parts[2:]))


def rubric_category_for(categories: Iterable[str]) -> tuple[str, bool]:
    """Pick the rubric category for a group. Returns (category, was_aliased).

    Prefers a category the rubric actually knows, by frequency. Only if the
    group has none does it fall back to aliasing an unroutable one — which is
    the case that would otherwise reach C6 with no rule to rate it.
    """
    counts = Counter(categories)
    routable = [(n, c) for c, n in counts.items() if c in RUBRIC_CATEGORIES]
    if routable:
        # Sort by count desc, then name, so ties are stable rather than
        # dependent on dict ordering.
        routable.sort(key=lambda nc: (-nc[0], nc[1]))
        return routable[0][1], False

    for category, _ in counts.most_common():
        if category in CATEGORY_ALIASES:
            return CATEGORY_ALIASES[category], True
    return "other", True


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def _is_token_prefix(shorter: tuple[str, ...], longer: tuple[str, ...]) -> bool:
    """True when `shorter` is a whole-token prefix of `longer`.

    Token-wise on purpose. A plain string prefix would let `nobu` absorb
    `nobuko`, and a name that merges two different people is worse than one
    that fails to merge two spellings of the same person: the first produces a
    confidently wrong dossier, the second only costs a search.
    """
    return len(shorter) < len(longer) and longer[: len(shorter)] == shorter


def group_mentions(mentions: Sequence[dict]) -> GroupResult:
    """Group mentions into entities. `mentions` are ResolvedElement dicts."""
    warnings: list[str] = []

    # ── seed: one bucket per normalised name ───────────────────────────
    seeds: dict[str, list[dict]] = {}
    parsed: dict[str, ParsedName] = {}
    for mention in mentions:
        name = parse_name(mention["canonical_name"])
        parsed.setdefault(name.normal, name)
        seeds.setdefault(name.normal, []).append(mention)

    groups: list[EntityGroup] = []
    for normal, bucket in seeds.items():
        category, aliased = rubric_category_for(m["category"] for m in bucket)
        groups.append(
            EntityGroup(
                canonical=normal,
                rubric_category=category,
                mentions=list(bucket),
                aliases={m["canonical_name"] for m in bucket},
            )
        )
        if aliased:
            raw = sorted({m["category"] for m in bucket})
            warnings.append(
                f"{normal}: no rubric category among {raw}; routed as {category}"
            )

    # ── pass 1: slug-core ──────────────────────────────────────────────
    groups = _merge(groups, parsed, _slug_core_target, warnings, "slug-core")
    # ── pass 2: qualifier link, requires co-occurrence ─────────────────
    groups = _merge(groups, parsed, _qualifier_target, warnings, "qualifier")

    # ── derive the surviving name ──────────────────────────────────────
    # The group's canonical must not be whichever alias happened to win the
    # merge race — that would make the cache key depend on the order the
    # model emitted its names in, which is the instability this module
    # exists to remove. Rebuild it from the group's own content instead.
    for group in groups:
        group.canonical = _derive_canonical(group)

    groups.sort(key=lambda g: (-len(g.mentions), g.canonical))
    return GroupResult(groups=groups, warnings=warnings)


def _derive_canonical(group: EntityGroup) -> str:
    """`{rubric_category}:{slug}[:{qualifier}]`, rebuilt from the aliases.

    A name carrying a qualifier wins the slug, because the qualifier marks
    the more specific record: `music:take_on_me:a_ha` is the work and
    `music:a_ha` is only its artist, so the work has to survive. Failing
    that, the shortest slug wins, which is the most general form of the
    entity — `coca_cola` rather than `coca_cola_polar_bear`.
    """
    names = [parse_name(alias) for alias in group.aliases]
    qualified = [n for n in names if n.qualifier]
    pick = min(qualified or names, key=lambda n: (len(n.tokens), n.slug))
    parts = [group.rubric_category, pick.slug]
    if pick.qualifier:
        parts.append(pick.qualifier)
    return ":".join(parts)


def _slug_core_target(source: EntityGroup, other: EntityGroup, parsed) -> bool:
    """Merge `source` into `other` on a shared slug core.

    Two cases:

    * `other`'s slug is a strict token prefix of `source`'s —
      `coca_cola_bottle` folds into `coca_cola`.

    * The slugs are identical and only the category prefix differs —
      `logo:coca_cola` and `trademark:coca_cola`. This is the case the
      category drift produces (the same line came back `trademark` on one
      run and `product` on the next), so it is the one that matters most.
      Direction is decided by name order purely so the merge is
      deterministic and cannot cycle; the surviving group's canonical is
      derived afterwards and does not depend on who won.
    """
    a, b = parsed[source.canonical], parsed[other.canonical]
    if _is_token_prefix(b.tokens, a.tokens):
        return True
    if a.tokens == b.tokens and a.qualifier == b.qualifier:
        return source.canonical > other.canonical
    return False


def _qualifier_target(source: EntityGroup, other: EntityGroup, parsed) -> bool:
    """Merge an artist-style name into the work that names it as qualifier.

    Requires the two to share a script element. Without that, `person:hopper`
    from an unrelated character would be swallowed by an Edward Hopper
    painting elsewhere in the script.
    """
    a, b = parsed[source.canonical], parsed[other.canonical]
    if not b.qualifier:
        return False
    if a.qualifier:
        return False  # a work does not fold into another work
    linked = b.qualifier == a.slug or b.qualifier in a.tokens
    return linked and bool(source.element_ids & other.element_ids)


def _merge(groups, parsed, wants_merge, warnings, label):
    """Fold groups together until nothing more merges."""
    changed = True
    while changed:
        changed = False
        for source in list(groups):
            if source not in groups:
                continue
            for other in groups:
                if other is source:
                    continue
                if wants_merge(source, other, parsed):
                    other.mentions.extend(source.mentions)
                    other.aliases |= source.aliases
                    # Recompute routing: the merged group may now contain a
                    # routable category the smaller one lacked.
                    other.rubric_category, _ = rubric_category_for(
                        m["category"] for m in other.mentions
                    )
                    warnings.append(
                        f"{label}: {source.canonical} -> {other.canonical}"
                    )
                    groups.remove(source)
                    changed = True
                    break
    return groups
