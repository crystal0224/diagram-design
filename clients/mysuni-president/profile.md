<!-- diagram-design-profile
name: mySUNI President Lecture 2026
slug: mysuni-president
source-url: none
created: 2026-08-15
updated: 2026-08-15
notes: Dark native-diagram skin aligned to artifact-template-mysuni-lecture-2026
-->
# Style Guide

This profile maps Diagram Design semantic roles to the governed
`mysuni-lecture-2026` native-diagram register. It is intended for browser studies,
SVG review, and visual QA. A finished lecture deck must rebuild meaning-bearing
geometry and text as editable PowerPoint objects.

## Tokens

### Semantic roles

| Role | Purpose | Default (light) | Default (dark) |
|---|---|---|---|
| `paper` | Page and slide field | `#071524` (body navy) | `#090635` (cover indigo) |
| `paper-2` | Semantic grouping surface | `#152334` | `#1B2A3C` |
| `ink` | Primary text and primary stroke | `#F7F9FC` | `#F7F9FC` |
| `muted` | Secondary text and default connector | `#9AA5B1` | `#AAB5C0` |
| `soft` | Tertiary labels and boundary notes | `#74879A` | `#8295A8` |
| `rule` | Hairline borders | `rgba(105,213,245,0.18)` | `rgba(105,213,245,0.20)` |
| `rule-solid` | Stronger boundaries and axes | `#29465C` | `#365A73` |
| `accent` | One selected concept or real relation | `#69D5F5` | `#69D5F5` |
| `accent-tint` | Fill for an accent boundary | `rgba(105,213,245,0.12)` | `rgba(105,213,245,0.14)` |
| `link` | External or cross-boundary relation | `#69D5F5` | `#87E0F8` |

The palette is intentionally narrow. Red and green are prohibited. Amber
`#D7A45A` is reserved for a concluding sentence or threshold and is not a second
diagram accent. A cyan line is allowed only when it is a connector, selected
boundary, axis, or another semantic relation; never add a standalone decorative
rail at the left or upper-left edge.

### Inversion rule (light -> dark)

This client profile is dark-first. Do not invert it into a light canvas during
normal lecture work. The `dark` column exists for schema compatibility and uses
the cover-indigo field; primary text stays white and cyan keeps the same role.

### Series palette (multi-series chart types only)

| Token | Light | Dark | Notes |
|---|---|---|---|
| `series-1` | `#4D718C` | `#6489A4` | Non-focal navy-blue series |
| `series-2` | `#7BAEC2` | `#93C6D8` | Non-focal pale-cyan series |
| `series-3` | `#D7A45A` | `#E0B873` | Conclusion/threshold only |
| `series-4` | `#9AA5B1` | `#B2BCC6` | Neutral comparison series |
| `series-5` | `#365A73` | `#52758E` | Structural series |

Series fills use 0.18 opacity. The focal series alone uses `accent`. Do not use
the series palette on ordinary concept nodes.

### Terminal skin (opt-in alternate)

The terminal skin remains opt-in and is not the lecture register.

| Token | Hex | Purpose |
|---|---|---|
| `terminal-page` | `#050C14` | Page behind the terminal window |
| `terminal-paper` | `#071524` | Window body |
| `terminal-bar` | `#0E1D2B` | Title bar |
| `terminal-border` | `#29465C` | Window border |
| `terminal-ink` | `#F7F9FC` | Primary text |
| `terminal-muted` | `#9AA5B1` | Secondary text |
| `terminal-soft` | `#74879A` | Tertiary text |
| `terminal-accent` | `#69D5F5` | One focal cue |
| `terminal-accent-tint` | `rgba(105,213,245,0.12)` | Focal fill |

## Typography

Browser studies use the PowerPoint unit conversion from the template contract:
`pt x 4/3 = CSS px`. Meaning-bearing text therefore starts at 23 px, equivalent
to the governed 17.25 pt floor.

| Role | Family | Size | Weight | Usage |
|---|---|---|---|---|
| `title` | Pretendard | 34px | 700 | Content title, one line when possible |
| `node-name` | Pretendard | 23px | 600 | Concept and state labels |
| `sublabel` | Pretendard | 23px | 400 | Short explanatory line |
| `eyebrow` | Pretendard | 23px | 600 | Section or semantic role label |
| `arrow-label` | Pretendard | 23px | 500 | Typed relation label |
| `callout` | NanumMyeongjo | 38px | 700 | One-line conclusion only |

### Font stack

```css
--font-sans: 'Pretendard Variable', Pretendard, 'Apple SD Gothic Neo', sans-serif;
--font-serif: NanumMyeongjo, 'Nanum Myeongjo', serif;
--font-mono: 'Pretendard Variable', Pretendard, sans-serif;
```

Do not introduce Calibri or Calibri Light. Classical original and conclusions may
use NanumMyeongjo. All other visible diagram copy uses Pretendard.

## Stroke, radius, spacing

| Token | Value | Use |
|---|---|---|
| `stroke-thin` | `1` | Hairline boundaries |
| `stroke-default` | `1.5` | Normal connectors and node borders |
| `stroke-strong` | `2` | Selected relation only |
| `radius-sm` | `4` | Small tags when semantically required |
| `radius-md` | `6` | Nodes |
| `radius-lg` | `8` | True grouping surfaces |
| `grid` | `4` | Every coordinate, size, and gap |

## Node type -> treatment

| Type | Fill | Stroke |
|---|---|---|
| `focal` | `accent-tint` | `accent` |
| `backend` | `paper-2` | `rule-solid` |
| `store` | `#0E1D2B` | `muted` |
| `external` | `#0B1A28` | `rule-solid` |
| `input` | `#102435` | `soft` |
| `optional` | `#0B1A28` | `soft` dashed `4,3` |
| `security` | `#102435` | `accent` dashed `4,4` |

Opaque shaded surfaces must encode grouping, hierarchy, comparison, or emphasis.
Do not repeat equal rounded boxes as decoration and do not nest cards.

## Canvas and geometry

- Primary study canvas: `1280 x 720` (`slide-16x9`).
- Working area: x `98..1176`, y `158..586`; reserve at least 80 px at bottom.
- Outer margin: at least 40 px; title and page furniture remain outside the SVG
  relationship field when the study is handed to PowerPoint.
- Three to seven meaning-bearing nodes per diagram. Above seven, split overview and
  detail instead of shrinking type.
- Connectors are orthogonal or purposefully curved, attached to declared anchors,
  and drawn before nodes. Every directional relation has a visible arrowhead.
- Labels never sit on top of a connector. Use a navy mask with 8–12 px breathing
  room when a relation label must cross a path.

## Accessibility and delivery boundary

- Every SVG uses `role="img"`, a resolving `aria-labelledby`, a first-child
  `<title>`, and a non-empty `<desc>`.
- HTML/SVG is the browser-review source of truth. PNG is a preview only.
- When a study enters a lecture deck, rebuild labels, connectors, boundaries,
  formulas, and nodes as editable PowerPoint objects. Never paste the browser
  screenshot as the construction layer.
