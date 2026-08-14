# frontend-design bridge — a diagram inside a designed page

The `frontend-design` skill exists to stop interfaces from reading as templated. This skill is, on
purpose, a template: one accent, a 4px grid, three families, twenty-seven fixed types. Put them
together carelessly and you get one of two failures — a distinctive page carrying a diagram that
looks like every other diagram-design diagram, or a diagram that adopts the page's boldness and
stops being readable.

The resolution is a split of authority, and it is not symmetric.

| | Owns | Never owns |
|---|---|---|
| **frontend-design** | palette, type personality, the page's signature moment, layout concept | diagram grammar, node budget, label geometry |
| **diagram-design** | which visual type, density, connector and label rules, the a11y contract | the palette, the type personality |

**The page's tokens win on color and type. The diagram's rules win on structure.** A diagram is a
figure inside the design, not another place to take a risk. `frontend-design` says to spend your
boldness in one place; if the page already has a signature element, the diagram is not it.

---

## Direction 1 — the page needs a diagram

`frontend-design` says nothing about diagrams, which means the default is whatever generic rounded
boxes come to hand. That is exactly the templated result the skill is trying to avoid.

1. Pick the type from [SKILL.md §3](../SKILL.md) — the behavior decides it, not the look.
2. Skin it from the page. If the design plan already names its 4–6 hex palette, map those onto the
   semantic roles directly. If the code exists, read it:

   ```bash
   python3 <skill-dir>/scripts/project_skin.py ./web
   python3 <skill-dir>/scripts/project_skin.py ./web --dark
   ```

   It scans CSS custom properties, Tailwind theme colors, and token files, then runs the **same**
   role mapping and the same gate as the brand bridge: AA on `ink` and `muted`, one accent, paper
   that is not pure white.
3. Keep the diagram's discipline even when the page is maximalist. Density stays 4/10. The accent
   still marks one or two focal nodes — a page with three brand colors does not license three
   accents inside the figure.
4. Take the page's *display* face for the diagram title only. Node labels stay in the utility/body
   face: a characterful display face at 12px in a 120px box is illegible, and `frontend-design`
   already says to use the display face with restraint.

---

## Direction 2 — the diagram needs a brand and the project has one

This is the common case and it has a clear precedence order:

1. **The project's own tokens** — `project_skin.py`. Nothing matches better than the codebase the
   diagram will live in.
2. **A named brand** — `design_md_skin.py` ([design-md-bridge.md](design-md-bridge.md)). Use when
   the diagram is for a client or deck rather than an app.
3. **A saved profile** — [profiles.md](profiles.md), for a skin you reach for repeatedly.
4. **Website onboarding** — [onboarding.md](onboarding.md), when only a public URL exists.

Reach down the list only when the step above has nothing to give.

---

## What the mapping cannot do, and what to do about it

`project_skin.py` reads names to assign roles, and a codebase does not name colors by role. Tailwind
calls a mid-neutral `slate-500`; an SVG token calls it `fill`. The measurement still holds — a color
either clears AA on paper or it doesn't — but the *naming* signal is often absent or actively
misleading, so the tool falls back to measurement alone and prints alternates.

Read the alternates column. The proposal is a starting point, not a verdict.

Two failures worth naming:

- **A gradient is not an accent.** Modern app palettes are full of gradient stops. The tool ranks by
  saturation, so a gradient endpoint can outrank the real brand color. If the app has one button
  color, that is the accent.
- **A dark-theme block read as the light palette.** The scanner drops declarations whose context
  says `dark` when building the light skin, but a project that themes by class rather than by name
  can defeat that. Check `paper` against what the app actually renders.

---

## Writing the labels

`frontend-design`'s writing guidance applies to diagram labels without modification, and it is
sharper than anything in this skill:

- Name things by what people control and recognize, never by how the system is built.
- Active voice; a label labels, and nothing quietly does double duty.
- Specific beats clever.

For Korean diagrams this compounds with [ko-typography.md §4](ko-typography.md): noun phrases, no
particles, no terminal punctuation, and genuine technical terms left in Latin. The two agree —
`frontend-design` says name things by what people recognize, and for a Korean engineering audience
that means `Kafka`, not `카프카`.

---

## Order of operations

Design the page first. The diagram inherits; it does not negotiate.

```
frontend-design: brief → design plan (palette, type, layout, signature) → build
                                    │
                                    ▼
diagram-design:  project_skin.py → semantic roles → type + density + labels
                                    │
                                    ▼
                 self_check · ko_check · verify-geometry · render_check --shot
                                    │
                                    ▼
                 embed_font.py --google-auto   (only when the file ships on its own)
```

Skip the last step for a diagram that lives inside the app — the page already loads its own fonts,
and inlining a second copy is dead weight. Reach for it when the diagram travels as a file.
