"""Show the margins derived from a screenplay, and how they were labelled.

    python api/scripts/inspect_margins.py                     # the fixture
    python api/scripts/inspect_margins.py path/to/script.pdf  # anything else
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.app.parser.margins import derive_margins  # noqa: E402
from api.app.parser.pdf import extract_lines  # noqa: E402

ROLES = ("action", "dialogue", "parenthetical", "character", "transition")


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "test_screenplay.pdf"
    if not target.exists():
        print(f"No such file: {target}")
        return 2

    lines = extract_lines(target)
    profile = derive_margins(lines)

    print(f"\n{target.name}")
    print(f"  {len(lines)} lines  ->  {profile.body_lines} body, "
          f"{profile.furniture_dropped} furniture, "
          f"{profile.slugs_excluded} numbered slug(s) excluded from the vote\n")

    print("DERIVED MARGINS")
    for role in ROLES:
        value = getattr(profile, role)
        if value is None:
            print(f"  {role:>14}  —")
        else:
            print(f"  {role:>14}  {value:>7.1f}pt   {value / 72:>5.2f}in")

    print("\nCLUSTERS (every margin found, labelled or not)")
    print(f"  {'x0':>8} {'inches':>7} {'lines':>6}  {'role':<14} sample")
    for c in profile.clusters:
        print(f"  {c.x0:>8.1f} {c.inches:>7.2f} {c.count:>6}  "
              f"{(c.role or '-'):<14} {c.sample[:40]!r}")

    if profile.notes:
        print("\nNOTES")
        for note in profile.notes:
            print(f"  - {note}")

    print(f"\nusable for classification: {profile.usable}")
    return 0 if profile.usable else 1


if __name__ == "__main__":
    sys.exit(main())