# Verify by rendering

**Run this before you hand a diagram over. Not instead of the static checkers — after them.**

[ADR 0005](../../../docs/adr/0005-label-geometry-is-verified.md) records how nine shipped examples
went out with clipped labels: every gate passed, because every gate read the source. The defect only
existed once a browser laid the file out. The lesson generalizes past that one bug — a static checker
has to *assume* the advance width, *assume* the font resolved, *assume* nothing moved under a
transform. A browser doesn't assume any of it.

## The loop

```bash
python3 <skill-dir>/scripts/self_check.py   diagram.html   # contract: a11y, single-file, motion
python3 <skill-dir>/scripts/ko_check.py     diagram.html   # Korean layer (skip for Latin-only)
python3 <repo>/scripts/verify-geometry.py   diagram.html   # label masks vs later-painted nodes
python3 <skill-dir>/scripts/render_check.py diagram.html --shot ./shots
```

Then **look at the PNG**. Not as a formality — the checkers cover what can be stated as a rule, and
density, balance, and whether the thing actually reads are not rules.

One-time setup for the last one: `pip install playwright && playwright install chromium` — the same
dependency PNG export already needs.

## What rendering proves that source-reading cannot

| Finding | Why only the browser knows |
|---|---|
| **Text overflow** | The real advance width of the font that actually loaded, after substitution, tspans, and transforms |
| **Font substitution** | Read over CDP `CSS.getPlatformFontsForNode`: the family and glyph count per label. A Hangul label silently served by Apple SD Gothic Neo looks correct on this Mac and wrong everywhere else |
| **Occlusion** | Real paint order and real boxes, including content inside transformed groups the static checker skips |
| **Horizontal page overflow** | `min-width: 900px` on the SVG against the frame at a given viewport |

The font check is the one worth internalizing. A missing webfont doesn't error — it falls back, and
the fallback is *installed on your machine*. Every local render looks fine. The file only breaks
after you've sent it.

## Reading the screenshot

The checkers are silent on everything below. Ask these yourself, against the image:

- **Density.** Target 4/10. Over nine nodes, it's probably two diagrams.
- **The accent.** One or two focal nodes. If coral appears five times, it has stopped meaning anything.
- **Whitespace.** Large dead bands at the top or bottom usually mean the `viewBox` is taller than the
  content — crop it (`viewBox="0 120 1000 288"`), don't pad the layout to fill it.
- **Balance.** Cards and columns of visibly unequal width read as a mistake unless the variation is
  deliberate and consistent.
- **Legibility at delivery size.** A diagram bound for a slide gets viewed at maybe 40% of what you
  see here. Squint at it. If the sublabels dissolve, they were decoration.

## When the file isn't local

`render_check.py` opens a `file://` URL in headless Chromium and needs nothing else. For a diagram
already served over http, or when you want to click through motion controls rather than measure a
static frame, drive it with `chromux` (`chromux launch <name>`, then
`CHROMUX_PROFILE=<name> chromux open <session> <url>`, then `chromux screenshot <session>`) or with
`browser-harness`. Same discipline either way: act, re-screenshot, and confirm the state changed
before assuming it did.
