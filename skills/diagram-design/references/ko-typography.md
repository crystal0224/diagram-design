# Korean (CJK) typography layer

**Load this whenever any label, title, sublabel, or legend in the diagram contains Hangul.**

The shipped skin is calibrated for Latin text: Instrument Serif / Geist / Geist Mono carry **no
Hangul glyphs**, and every width budget in `SKILL.md` (`≤14 characters` arrow labels, `120px` node
boxes) assumes a Latin advance of roughly `0.5em` per character. A Hangul syllable advances a full
`1.0em`. Drop Korean into the default skin and you get two failures at once: tofu or an unplanned
system fallback, and labels that run past the box they sit in.

This file is the Korean layer. It changes fonts, size floors, and width budgets. **It changes no
colors** — the palette, the one-accent rule, and every token in
[`style-guide.md`](style-guide.md) stay exactly as they are.

---

## 1. Font stack

Replace the stylesheet link and the three font variables in the template:

```html
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&family=IBM+Plex+Sans+KR:wght@400;500;600&family=Noto+Serif+KR:wght@400;500&display=swap" rel="stylesheet">
```

```css
--font-sans:  'Geist', 'Pretendard Variable', Pretendard, 'IBM Plex Sans KR', system-ui, sans-serif;
--font-serif: 'Instrument Serif', 'Noto Serif KR', serif;
--font-mono:  'Geist Mono', 'IBM Plex Sans KR', ui-monospace, monospace;
```

**Why this order.** CSS font fallback resolves *per glyph*, not per element. Latin keeps Geist and
Instrument Serif exactly as designed; only Hangul falls through to the next family that covers it.
Nothing about the Latin rendering changes.

`Pretendard Variable` sits ahead of the webfont because it is installed locally on this machine and
is the better Hangul companion to Geist — but it is a **local name only**, never a CDN link, so a
file handed to someone else silently degrades to `IBM Plex Sans KR` from Google Fonts and still
renders correctly. That keeps the single-file / approved-remote-asset contract intact
(`self_check.py` only permits `fonts.googleapis.com/css2`).

Never add a `@font-face` block pointing at jsDelivr, unpkg, or a raw GitHub URL for Pretendard.
`self_check.py` fails the file, and the diagram breaks the moment that CDN moves.

### Making Pretendard travel — subset embedding

Pretendard is not on Google Fonts, so the stack above gets you Pretendard on a machine that has it
installed and `IBM Plex Sans KR` everywhere else. When the diagram is a deliverable and you want the
same rendering on the recipient's screen, embed it:

```bash
python3 <skill-dir>/scripts/embed_font.py diagram.html            # subset + inline
python3 <skill-dir>/scripts/embed_font.py diagram.html --check     # is the subset current?
```

The usual objection to embedding CJK is size — a full Hangul face is 1.5 MB. It doesn't apply here.
A diagram carries a few dozen distinct characters, so subsetting to the text actually present costs
**about 11 KB per weight**; a three-weight Korean diagram goes from 7 KB to roughly 54 KB total, with
no remote dependency at all. That is a stronger single-file guarantee than the Google Fonts link.

Two things to keep straight:

- **Re-run after editing any label.** The subset is built from the text present at the time. New
  characters are simply absent and fall back silently. `--check` decodes the embedded faces and
  compares their cmap against the document, so staleness is a hard failure rather than a warning.
- **Embedding is redistribution.** Pretendard is OFL-1.1 and permits it. Check the license before
  pointing `--family` at anything else.

### SVG `<text>` elements

SVG text does not inherit the CSS variables unless you say so. Every `<text>` that can carry Hangul
must name the stack explicitly:

```svg
<text font-family="'Geist', 'Pretendard Variable', Pretendard, 'IBM Plex Sans KR', sans-serif" …>
```

A bare `font-family="'Geist', sans-serif"` on a Hangul label is the single most common defect —
it renders through the generic `sans-serif`, which on macOS is Helvetica → Apple SD Gothic Neo, a
different skeleton and a different advance width than the one you laid the box out for.

### Document language

Set `<html lang="ko">` when the diagram is predominantly Korean. This is not cosmetic: it selects
Korean glyph forms in fonts that share CJK codepoints, and it tells screen readers which voice to
use on the `<title>` / `<desc>` accessibility text.

---

## 2. Size floors — Hangul never below 12px

The Latin ramp descends to 7px for eyebrows and 8px for arrow labels. Hangul at those sizes is a
grey smudge: a syllable packs two to three strokes into the same box a Latin letter uses for one.

| Role | Latin (unchanged) | **Hangul floor** | Notes |
|---|---|---|---|
| `title` | 1.75rem | 1.75rem | serif; no change |
| `node-name` | 12px | **12px** | 16px for focal nodes if the box allows |
| `sublabel` | 9px | **12px** | keep Latin technical strings (ports, URLs, types) at 9px mono |
| `eyebrow` | 7–8px | **12px** | see tracking rule below |
| `arrow-label` | 8px | **12px** | mask rect must grow with it — §3 |
| `legend` | 8px | **12px** | |

12px is the next value up the allowed ramp (`8, 12, 16, 20, …`), so the 4px-grid rule in `SKILL.md`
§7 holds without exception. **There is no 9px or 10px Hangul.** If a 12px label doesn't fit, the box
is too small or the label is too long — fix the layout, never the floor.

> This floor is the diagram-side expression of the `오밀조밀` failure: fonts and padding shrunk to
> make a layout fit, at the cost of legibility. Growing the node is always the correct fix.

### Tracking and case

- **`letter-spacing: 0.18em` is for Latin eyebrows only.** On Hangul it opens gaps between syllables
  that read as broken spacing. Use `0.02em`–`0.06em`, or none.
- **`text-transform: uppercase` is a no-op on Hangul** and still uppercases any Latin mixed into the
  same string, producing `데이터 PIPELINE`. Drop it from Korean eyebrows; write the Latin in the
  case you actually want.
- Mixed Korean-Latin eyebrows keep one size for both. Don't shrink the Latin half to "balance" it.

---

## 3. Width budgets — the character count is not the same number

Every width budget in `SKILL.md` was measured in Latin characters. Convert before you use it.

**Rule of thumb: one Hangul syllable ≈ two Latin characters.**

Working formula for a centered label in a box:

```
usable width = node width − 2 × padding      (padding = 12 or 16)
max Hangul syllables = floor(usable width / font size)
```

At 12px, on the standard node ramp:

| Node width | Usable (16px padding) | Max Hangul | Max Latin (for comparison) |
|---|---|---|---|
| 96 | 64 | **5** | 11 |
| 120 | 88 | **7** | 15 |
| 140 | 108 | **9** | 18 |
| 160 | 128 | **10** | 22 |
| 200 | 168 | **14** | 29 |
| 240 | 208 | **17** | 36 |

Consequences you have to act on, not just know:

1. **Arrow labels: `≤14 characters` becomes `≤7 Hangul syllables`.** And the mask rect underneath
   grows with it — the shipped snippet hardcodes `width="36"`, which fits three Hangul syllables at
   12px, not seven. Size it as `syllables × font-size + 8`, then re-center: `x = MID_X − width/2`.
2. **The default node width for Korean architecture diagrams is 140 or 160, not 120.** A 120px box
   holds `인증 서버` (4) comfortably and `데이터 파이프라인` (8) not at all.
3. **Two-line labels beat one long line.** Use a second `<tspan>` at `dy="16"` and grow the node
   height by 16, rather than shrinking the font or widening the box past its neighbours.
4. **Don't romanize to make it fit.** `Auth 서버` to save four pixels reads as a translation
   artifact. Widen the box.

### HTML text blocks (summary cards, legend prose, captions)

```css
word-break: keep-all;
overflow-wrap: break-word;
line-height: 1.7;
```

`keep-all` stops the browser from breaking a Korean line mid-word, which is the default and is
wrong — Korean wraps at 어절 (word-spacing) boundaries. `overflow-wrap: break-word` is the escape
hatch for a single unbreakable token (a long URL) so `keep-all` can't cause horizontal overflow.
`line-height` goes to 1.7 because Hangul has taller effective x-height than Latin at the same size;
1.4 reads cramped.

---

## 4. Wording — the labels themselves

Layout rules don't fix a label that sounds like machine translation.

- **Noun phrases, no particles.** `사용자 인증`, not `사용자를 인증한다`. Diagram labels are names,
  not sentences. A trailing `-하기` / `-처리` is usually removable.
- **No terminal punctuation** in node names or arrow labels.
- **Keep genuine technical terms in Latin.** `Kafka`, `OAuth 2.0`, `S3`, `REST API`, `p95` — these
  are names, and transliterating them (`카프카`) makes the diagram harder to read for the exact
  audience who needs it. Translate *concepts* (`처리량`, `적재`, `정합성 검증`), keep *identifiers*.
- **One term per concept across the whole diagram.** If a box says `적재` the legend cannot say
  `로딩`. Pick one and sweep the file.
- **Avoid the 딱딱한 문어체 register** — `~를 수행함`, `~에 대한`, `~에 있어서`. A diagram label is
  closer to spoken shorthand than to a formal report: `일 배치 적재`, not `일 단위 배치 적재의 수행`.

---

## 5. Pre-output gate

Run the mechanical checker before you hand the file over. It measures rather than reviews:

```bash
python3 <skill-dir>/scripts/ko_check.py my-diagram.html
python3 <skill-dir>/scripts/embed_font.py my-diagram.html --check   # if the file is a deliverable
```

It reports, with numbers:

- Hangul text below the 12px floor
- Hangul labels whose estimated advance width overruns the box or mask they sit inside
- `<text>` elements carrying Hangul with a font stack that has no Hangul coverage
- `letter-spacing` above `0.08em` on Hangul, and `text-transform: uppercase` on Korean strings
- `lang` not set to `ko` on a predominantly Korean document
- HTML text blocks missing `word-break: keep-all`

It is deliberately conservative: a label is only reported as overflowing when a rect actually
contains its anchor point, so free-floating titles, axis labels, and legend rows never produce
noise. Run it alongside — not instead of — `self_check.py` and `verify-geometry.py`, then render
the file and look at it ([`verify-render.md`](verify-render.md)). The estimator is good to a few
percent; the browser is the authority.
