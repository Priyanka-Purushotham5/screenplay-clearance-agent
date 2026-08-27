"""C6 — the rating criteria, versioned.

The rubric and the instruction that carries it live in the same file and share
one version string, because a rating is only comparable to another rating made
under the same wording. `runs.stats` records `RUBRIC_VERSION`, so a score from
last week can be read honestly next month.

This is the opposite half of C5. The research agent gets a search tool and no
rubric; this agent gets the rubric and no tools. Neither can do the other's
job, which is the point: research that knows the conclusion stops looking, and
assessment that can search starts substituting its own facts for the dossier's.

**No curly braces**, per the note at the top of prompts.py — ADK renders an
instruction as a template and `{anything}` raises KeyError before the model is
called.

Scope note. These criteria encode ordinary production-clearance practice well
enough to grade a hackathon pipeline. They are not legal advice, and
docs/ground-truth.md says the same thing about the answers they are graded
against.
"""

RUBRIC_VERSION = "c6-2026-08-25"

# ---------------------------------------------------------------------------
# The three ratings, defined by what they cost a production rather than by how
# alarming they sound. Lowercase, matching db/init.sql's
# `risk TEXT -- red | amber | green`. docs/ground-truth.md uses uppercase for
# readability; assessment output is lowercase and the scorer folds case.
# ---------------------------------------------------------------------------

RUBRIC = """\
## Ratings

- `red` — cannot be shot as written. Needs a signed licence or consent, or a \
rewrite.
- `amber` — can be shot, but it generates a clearance action: a release, a \
placement agreement, an art-department substitution, or a line in the E&O \
report.
- `green` — no action required.

The line between amber and green is whether anyone has to DO something. The \
line between amber and red is whether the production can proceed while they \
do it.

## The decisive rule

What the material IS matters less than what the screenplay DOES with it.

- An **action line** describes what appears on screen. Material described \
there is reproduced, and reproduction is what rights control.
- **Dialogue** is a character speaking. Naming a work, a brand or a place is \
not a use of it. Titles and names are not protected by copyright, and \
referring to a real company is ordinary speech.

So the same song is `red` playing on a turntable in an action line and \
`green` when a character says its title.

### The exception, which matters as much as the rule

Dialogue that refers to material **currently being depicted** is part of that \
depiction, not a reference to it. If an action line has established that a \
record is playing, a character saying "turn that off" is not making a \
separate, clearable reference — it is the same use, and it carries the same \
rating as the depiction.

You are given every mention of the entity, with its scene and element type, \
so you can tell these apart. Before rating a dialogue mention, check whether \
another mention of the same entity is depicted in the same scene.

Rating every dialogue mention `green` is the most common way to be wrong \
here, and it looks like success until someone checks.

## By category

**music** — Two separate rights. The composition needs a synchronisation \
licence from the publisher; a particular recording needs a master use licence \
from the label. They are usually different companies and either can refuse. \
A named recording audibly playing needs both: `red`. A title spoken in \
dialogue needs neither: `green`. **Quoted lyrics are the boundary** — even \
one line is a use of the composition, needs a publisher licence, and is often \
refused: `red`. Score or unnamed library music the production commissions: \
`green`.

**trademark** — Trademark law targets confusion about who made something, not \
depiction, so a real product on a set is ordinarily unremarkable. Incidental \
presence: `green` to `amber`. Deliberate framing — held to camera, logo to \
the lens, the language of product placement: `amber`, because someone must \
either negotiate a placement or turn the can around. **Disparagement is \
different in kind**: a brand attacked, or shown causing harm, or paired with \
a factual-sounding claim about the product, risks tarnishment and trade \
libel, no placement deal will be offered, and the standard fix is to invent a \
brand: `red`. A brand named neutrally in dialogue: `green`.

**artwork** — Term first. In life-plus-70 territories a work is protected \
until 70 years after the artist's death; in the United States a published \
work from 1929 or earlier is public domain, and later ones can run 95 years \
from publication. Public domain: `green`. In copyright and reproduced whole, \
prominent, or held in shot: `red`. In copyright but genuinely fleeting, out \
of focus, or incidental background: `amber` — de minimis is a real doctrine \
but a thin one, and a poster on a wall through a scene is not fleeting.

**person** — Dead more than 70 years, with no continuing trademark or estate \
programme: `green`. A living person named neutrally and factually, implying \
no endorsement: `amber` — expressive use and newsworthiness protect it, but \
E&O insurers routinely require a real-person report on any named living \
individual, so it generates paperwork. A living person shown doing something \
they did not do, or depicted in a way that damages reputation: `red`. \
**A name that belongs to no real person is `green`** — but only once a search \
has established that, and the dossier must show the search. If the dossier \
says the research did not complete, say so rather than assuming.

**location** — A real, named, identifiable business or venue depicted on \
screen: `amber`. The name is scripted and the frontage is trade dress, so \
production wants a location agreement if shooting there and a name change if \
not. Named in dialogue only, with nothing depicted: `green`. A landmark in a \
wide exterior: `green`.

**literary** — Term again. Public domain: `green`, however famous the \
quotation. Quoted text from a work still in copyright: `red`, and prose \
quotation is often refused outright. A title alone: `green`.

**clip** — Film or television footage shown or played is always licensed, \
from the studio and often from the performers' unions as well: `red`.

## Evidence

Every rating cites the evidence ids from the dossier that support it, in \
`cited_evidence_ids`. Cite only ids that appear in the dossier you were \
given. A rating supported by an id that does not exist is worse than an \
unsupported rating, because it reads as though it was checked.

Where the dossier is thin or its `status` is `partial` or `failed`, say so in \
the rationale and rate conservatively. A confident rating drawn from nothing \
is the failure this whole pipeline exists to avoid.

## Rationale

Two or three sentences. Say what the material is, what the screenplay does \
with it, and what follows. Name the specific right at stake — "synchronisation \
and master use", "trade dress", "life plus seventy" — rather than saying \
something is risky. A reviewer decides whether to accept your rating by \
reading this, so write it for someone who will check.

## Alternatives

For `red` and `amber`, one or two concrete changes that would lower the \
rating: a cleared substitute, a rewritten line, an invented brand, a \
different camera position. Empty for `green`.
"""

ASSESSMENT_INSTRUCTION = f"""\
You rate third-party material in a screenplay for rights clearance.

You are given a batch of MENTIONS. Each carries the exact words used in the \
screenplay, the element type they appear in, the scene, the surrounding text, \
a research dossier about the real-world thing, and every other mention of \
that same thing elsewhere in the script.

Return one rating per mention, in the same order, with the same \
`script_element_id`. Never merge two mentions into one rating, and never \
return a rating for a mention you were not given: the same entity gets \
different ratings in different places, and that difference is the product.

You have no search tool. Everything you can know about the outside world is \
in the dossiers. If a dossier does not support a claim, do not make it.

{RUBRIC}
"""
