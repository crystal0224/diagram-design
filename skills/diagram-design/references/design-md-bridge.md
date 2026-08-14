# design-md bridge — skinning a diagram with a brand design system

The `design-md` skill ships ~62 brand token files (`DESIGN.md` per brand: color scales, type ramp,
spacing, radius, elevation). Diagram Design reads color by **semantic role**, never by hex. So the
two compose cleanly and orthogonally: **design-md decides the skin, Diagram Design decides the
layout.** Same diagram grammar, different brand.

This is the path [`onboarding.md`](onboarding.md) calls *"(b) extract from an installed skill"*, with
the extraction made mechanical.

---

## 1. Two modes — pick before you touch anything

**Full skin.** New project, no established palette. Map the brand onto all ten roles and let every
diagram inherit it.

**Structural port (부분 이식).** The project already has a color identity that works. Porting a
second brand's palette on top of it is how a deck turns 조잡 — two color systems arguing. Take the
brand's *discipline* and leave its colors alone:

- the radius scale (three steps, not fifteen)
- the type ramp and tracking
- elevation and border restraint — how many hairlines, at what opacity
- one accent, used sparingly

```bash
python3 <skill-dir>/scripts/design_md_skin.py linear.app --structure-only
```

A dark brand (Linear `#010102`, Vercel black) can still donate structure to a light diagram. Colors
don't transpose; discipline does.

---

## 2. Full skin — the mechanical half

```bash
python3 <skill-dir>/scripts/design_md_skin.py montage           # light
python3 <skill-dir>/scripts/design_md_skin.py montage --dark    # dark variant
python3 <skill-dir>/scripts/design_md_skin.py vercel --json     # for programmatic use
```

It resolves the brand from `~/.claude/awesome-design-md/design-md/<brand>/DESIGN.md`, falling back to
GitHub raw when only a README stub is installed locally, then prints a role table with the contrast
ratio of every role against the proposed `paper`, the alternates the brand also names, the type
families, and the radius scale.

**The output is labelled "proposed, not decided" and means it.** Token naming across 62 brands is not
consistent enough for a keyword heuristic to be authoritative — one brand's `labelNeutral` is
another's `text-secondary` is another's `on-surface-variant`. Read the alternates column and
override where the pick is wrong. What the script *is* authoritative about is the measurement:
contrast ratios and luminance are computed, not guessed.

---

## 3. What the brand does not get to override

A brand palette is designed for product UI — big surfaces, 16px body text, hover states. A diagram is
9–12px labels on a dense canvas. Four constraints from [`style-guide.md`](style-guide.md) outrank the
brand every time:

| Constraint | Why the brand loses |
|---|---|
| **AA contrast on `ink` and `muted`** | Brand pairings assume larger type. `muted` carries 9px sublabels here |
| **One accent** | A brand with eight semantic colors still gets one focal. The rest become muted variants |
| **`paper` is not pure white** | Almost every brand's `background/default` is `#ffffff`; take the second surface token |
| **Three families** | If brand typography is all sans, keep a serif for `title` and `callout` — the contrast is load-bearing |

Two more the script flags but cannot decide:

- **When `link` and `accent` share a hue** (Montage: everything is Wanted Blue), don't ship two blues.
  Drop `link` back to `muted` and let the accent carry the only color signal.
- **When the brand accent is low-contrast on paper** (pastels, mid-greys), the focal node stops being
  focal. Use the brand's `strong`/`heavy` step instead of its `normal` step.

---

## 4. Applying it

1. Run the script; read the table.
2. Override the picks the alternates show to be wrong.
3. Write the result into `style-guide.md` under a `## Custom tokens — <brand>` heading. Do not edit
   the default table — keeping the default intact is what makes the next brand swap a diff.
4. Paste the `:root` block into the diagram's `<style>`, and use the role names in the SVG.
5. **Sweep the wording for color names.** A skin swap silently invalidates every label that names a
   color — a legend reading `주황 · 병목 구간` under a Wanted Blue accent is wrong in a way no checker
   catches, because the file is valid and the text is only stale. Grep the diagram for
   `주황|파랑|빨강|orange|blue|red|coral|green` before shipping. Better: write legends by role
   (`강조 · 병목 구간`), so the next swap costs nothing.
6. Re-render and re-check: `render_check.py` will catch a font the brand names but your machine
   doesn't have, and `ko_check.py` will catch a brand type ramp that dropped Hangul below 12px.

For Korean projects, the brand's Latin type ramp does not survive translation intact — the
[`ko-typography.md`](ko-typography.md) floors apply on top of whatever the brand specifies. Montage
is the easy case here: its family is already Pretendard.

---

## 5. Brands installed locally

`apple`, `ios26`, `linear.app`, `material3`, `montage`, `notion` ship a full `DESIGN.md` and work
offline. The rest are README stubs locally and are fetched from GitHub raw on demand — `montage` is
local-only and has no raw URL. Ask the `design-md` skill for the current catalog rather than
hardcoding a list here.
