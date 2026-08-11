"""
make_test_pdf.py — generates docs/test_screenplay.pdf

A ~4-page properly formatted screenplay containing:
  - INT./EXT. and I/E. headings
  - A mini-slug (ANGLE ON) that should NOT be treated as a new scene
  - Page-split dialogue simulation
  - A song in an action line (sync rights needed)
  - The same song referenced in dialogue (reference only)
  - A named brand held to camera
  - A real painting on a wall
  - A living public figure named in dialogue
  - A real restaurant as a location
  - A line of Shakespeare

These are the planted elements from B7 in implementation-checklist.md.
Ground truth for expected ratings is in docs/ground-truth.md (to be written).

Run:
    python api/scripts/make_test_pdf.py
Output: docs/test_screenplay.pdf
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "test_screenplay.pdf"

# ---------------------------------------------------------------------------
# Screenplay layout constants (standard spec)
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = letter          # 8.5 x 11 inches
LEFT   = 1.5 * inch              # action / scene heading left margin
RIGHT  = PAGE_W - inch           # right margin
TOP    = PAGE_H - inch           # top of text area
BOTTOM = inch                    # bottom of text area

CHAR_X   = 3.7 * inch            # character cue indent
DIAL_L   = 2.5 * inch            # dialogue left
DIAL_R   = PAGE_W - 2.5 * inch  # dialogue right
PAREN_X  = 3.0 * inch            # parenthetical indent

LINE_H   = 14                    # points between lines (12pt Courier)
FONT     = "Courier"
FONT_B   = "Courier-Bold"
SIZE     = 12


class ScreenplayPDF:
    def __init__(self, path: Path):
        self.c = canvas.Canvas(str(path), pagesize=letter)
        self.c.setFont(FONT, SIZE)
        self.y = TOP
        self.page = 1
        self._draw_page_number()

    # ------------------------------------------------------------------
    # Primitives
    # ------------------------------------------------------------------
    def _draw_page_number(self):
        if self.page > 1:
            self.c.setFont(FONT, SIZE)
            self.c.drawRightString(RIGHT, PAGE_H - 0.6 * inch,
                                   f"{self.page}.")

    def _newline(self, n=1):
        self.y -= LINE_H * n

    def _new_page(self):
        self.c.showPage()
        self.page += 1
        self.y = TOP
        self._draw_page_number()
        self.c.setFont(FONT, SIZE)

    def _check_page(self, lines_needed=3):
        if self.y - LINE_H * lines_needed < BOTTOM:
            self._new_page()

    # ------------------------------------------------------------------
    # Screenplay elements
    # ------------------------------------------------------------------
    def scene_heading(self, text: str):
        self._check_page(4)
        self._newline(2)
        self.c.setFont(FONT_B, SIZE)
        self.c.drawString(LEFT, self.y, text.upper())
        self.c.setFont(FONT, SIZE)
        self._newline()

    def action(self, text: str):
        """Word-wrap action lines to the text column width."""
        self._check_page(2)
        self._newline()
        max_chars = int((RIGHT - LEFT) / (SIZE * 0.6))
        for line in self._wrap(text, max_chars):
            self._check_page()
            self.c.drawString(LEFT, self.y, line)
            self._newline()

    def character(self, name: str):
        self._check_page(3)
        self._newline()
        self.c.drawString(CHAR_X, self.y, name.upper())
        self._newline()

    def parenthetical(self, text: str):
        self.c.drawString(PAREN_X, self.y, f"({text})")
        self._newline()

    def dialogue(self, text: str):
        max_chars = int((DIAL_R - DIAL_L) / (SIZE * 0.6))
        for line in self._wrap(text, max_chars):
            self._check_page()
            self.c.drawString(DIAL_L, self.y, line)
            self._newline()

    def transition(self, text: str):
        self._newline()
        self.c.drawRightString(RIGHT, self.y, text.upper())
        self._newline()

    def mini_slug(self, text: str):
        """A non-scene ALL-CAPS line — should NOT create a new scene."""
        self._check_page(2)
        self._newline()
        self.c.setFont(FONT_B, SIZE)
        self.c.drawString(LEFT, self.y, text.upper())
        self.c.setFont(FONT, SIZE)
        self._newline()

    def save(self):
        self.c.save()

    @staticmethod
    def _wrap(text: str, width: int) -> list[str]:
        words = text.split()
        lines, current = [], ""
        for word in words:
            if len(current) + len(word) + (1 if current else 0) <= width:
                current = f"{current} {word}".strip()
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [""]


# ---------------------------------------------------------------------------
# Build the screenplay
# ---------------------------------------------------------------------------
def build(pdf: ScreenplayPDF):

    # --- Scene 1 ---
    pdf.scene_heading("INT. RECORD LABEL OFFICE - DAY")
    pdf.action(
        "A cluttered A&R office. Gold records line the walls. "
        "On a battered turntable, 'Take On Me' by a-ha plays loudly -- "
        "that unmistakable synth riff filling the room."
        # ↑ PLANTED: song in action line → RED (sync rights needed)
    )
    pdf.action(
        "DIANA (40s, sharp) stands at the window, back to us. "
        "Her assistant, FELIX (20s, nervous), hovers in the doorway."
    )
    pdf.character("FELIX")
    pdf.dialogue(
        "The Nielsen rep is here. And... he brought lawyers."
    )
    pdf.character("DIANA")
    pdf.dialogue(
        "Of course he did. Turn that off."
    )
    pdf.action("Felix crosses to the turntable and lifts the needle.")

    # --- Mini-slug — must NOT become a new scene ---
    pdf.mini_slug("ANGLE ON -- THE TURNTABLE")
    pdf.action(
        "The spinning vinyl slows. The label reads: "
        "WEA International. A Coca-Cola can sits beside it, "
        "logo facing the lens."
        # ↑ PLANTED: named brand held to camera → AMBER (depiction)
    )

    # --- Scene 2 ---
    pdf.scene_heading("INT. RECORD LABEL OFFICE - CONTINUOUS")
    pdf.action(
        "Diana turns. On the wall behind her hangs Nighthawks by Edward Hopper, "
        "a large print in a thin black frame."
        # ↑ PLANTED: 20th-century painting on wall → RED (Hopper died 1967, within 70yr)
    )
    pdf.character("DIANA")
    pdf.dialogue(
        "You know that song? Take On Me? I actually love that song. "
        "It reminds me why I got into this business."
        # ↑ PLANTED: same song in dialogue → GREEN (reference only, no sync)
    )
    pdf.character("FELIX")
    pdf.dialogue(
        "The Nielsen rep -- his name is Harman. Marcus Harman."
    )
    pdf.character("DIANA")
    pdf.parenthetical("dry")
    pdf.dialogue(
        "The Marcus Harman? I thought he retired."
    )

    # --- Scene 3: INT./EXT. heading edge case ---
    pdf.scene_heading("INT./EXT. DIANA'S CAR - MOVING - LATE AFTERNOON")
    pdf.action(
        "Diana drives. Felix rides shotgun, scrolling his phone. "
        "They pass a brightly lit Nobu restaurant -- Diana glances at it."
        # ↑ PLANTED: real restaurant as location → AMBER (trade dress)
    )
    pdf.character("FELIX")
    pdf.dialogue(
        "He says the Coca-Cola deal is dead. They found out about the "
        "Pepsi placement last quarter. Now they're threatening to pull "
        "their entire catalog."
        # ↑ PLANTED: brand used in context of dispute → RED (disparagement adjacent)
    )
    pdf.character("DIANA")
    pdf.dialogue(
        "To be, or not to be -- that is the question. "
        "Shakespeare said that and it's still the only thing "
        "worth saying in a negotiation."
        # ↑ PLANTED: line of Shakespeare → GREEN (public domain)
    )

    # --- Scene 4 ---
    pdf.scene_heading("INT. LAW FIRM - CONFERENCE ROOM - NIGHT")
    pdf.action(
        "A long glass table. MARCUS HARMAN (60s, silver-haired, "
        "the actual music industry executive) sits at one end."
        # ↑ PLANTED: living public figure named in dialogue → AMBER (mention)
    )
    pdf.action(
        "Across from him, Diana. Between them, a stack of contracts. "
        "A framed poster of Guernica by Pablo Picasso dominates the far wall."
        # ↑ NOTE: Picasso died 1973 -- Guernica copyright held by Picasso estate
        # until 2044. This is another RED painting element.
    )
    pdf.character("MARCUS")
    pdf.dialogue(
        "Your client Dr. James Holloway signed a personal guarantee. "
        "The debt is real."
        # ↑ PLANTED: fictional doctor with plausible real name → the hard one
    )
    pdf.character("DIANA")
    pdf.dialogue(
        "Dr. Holloway disagrees. And frankly, so do I."
    )
    pdf.character("MARCUS")
    pdf.dialogue(
        "Then we'll let the courts decide. "
        "I've been doing this for forty years. "
        "I have never lost a contract dispute."
    )
    pdf.character("DIANA")
    pdf.dialogue(
        "There's always a first time."
    )

    # --- I/E. heading edge case ---
    pdf.scene_heading("I/E. PARKING GARAGE - NIGHT")
    pdf.action(
        "Diana walks to her car alone. Her footsteps echo. "
        "She stops at a concrete pillar. Leans against it. Closes her eyes."
    )
    pdf.mini_slug("MOMENTS LATER")   # another mini-slug — not a new scene
    pdf.action(
        "She opens her eyes. Takes out her phone. Dials."
    )
    pdf.character("DIANA")
    pdf.parenthetical("into phone")
    pdf.dialogue(
        "It's me. We need to talk about the Holloway situation. "
        "Meet me at Nobu. Twenty minutes."
    )

    pdf.transition("FADE OUT.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = ScreenplayPDF(OUTPUT)
    build(pdf)
    pdf.save()
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Written: {OUTPUT}  ({size_kb:.1f} KB)")
    print(f"Pages  : {pdf.page}")
    print()
    print("Planted elements:")
    print("  RED   - 'Take On Me' by a-ha in action line (sync rights)")
    print("  GREEN - 'Take On Me' referenced in dialogue (no sync)")
    print("  AMBER - Coca-Cola can held to camera (brand depiction)")
    print("  RED   - Nighthawks by Hopper on wall (Hopper died 1967, within 70yr)")
    print("  AMBER - Nobu restaurant as location (trade dress)")
    print("  GREEN - Shakespeare quote (public domain)")
    print("  AMBER - Marcus Harman (living public figure, named in dialogue)")
    print("  HARD  - Dr. James Holloway (fictional doctor, plausible real name)")
    print("  EXTRA - Guernica / Picasso (died 1973, estate holds until 2044)")
    print()
    print("Parser edge cases:")
    print("  - ANGLE ON mini-slug (must NOT create a new scene)")
    print("  - MOMENTS LATER mini-slug (must NOT create a new scene)")
    print("  - INT./EXT. heading")
    print("  - I/E. heading")


if __name__ == "__main__":
    main()
