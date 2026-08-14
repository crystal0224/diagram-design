#!/usr/bin/env python3
"""Render a diagram in a real browser and measure it, instead of reviewing it.

    python3 <skill-dir>/scripts/render_check.py my-diagram.html
    python3 <skill-dir>/scripts/render_check.py my-diagram.html --shot out/

Requires the same one-time setup as PNG export:

    pip install playwright && playwright install chromium

ADR 0005 settled that geometric defects survive review because they are only
visible once rendered. `verify-geometry.py` and `ko_check.py` both work from the
source text and must therefore estimate — advance widths, transform-free
coordinates, an assumed font. This checker skips the estimate: it loads the file
in Chromium, waits for webfonts to settle, and reads back real boxes.

Three things it can prove that no static checker can:

  * **Text overflow** — the actual rendered box against the actual node box,
    with transforms, tspans, and font substitution all already applied.
  * **Font substitution** — the family the browser really used for each label,
    via CDP `CSS.getPlatformFontsForNode`. A Hangul label falling back to
    Apple SD Gothic Neo looks fine on this Mac and breaks on every other
    machine; here it is a named, reported fact.
  * **Occlusion** — a label covered by a node painted after it, including
    content inside transformed groups that the static checker skips.

Exit code 1 on errors. Screenshots are written only when --shot is given.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HANGUL_RE = re.compile(r"[가-힣ᄀ-ᇿ]")
CJK_RE = re.compile(r"[가-힣ᄀ-ᇿ一-鿿぀-ヿ]")

# Overflow tolerance: a rendered box may sit this many px past its container
# before it counts as an overrun. Antialiasing and hinting cost ~1px.
EDGE_TOLERANCE_PX = 1.5
# A node must cover at least this share of a label's area to count as occluding.
OCCLUSION_MIN_RATIO = 0.15

EXTRACT_JS = r"""
() => {
  const all = Array.from(document.querySelectorAll('*'));
  const order = new Map(all.map((el, i) => [el, i]));
  const out = { texts: [], rects: [], viewport: {
      w: document.documentElement.scrollWidth,
      h: document.documentElement.scrollHeight } };
  for (const svg of document.querySelectorAll('svg')) {
    const svgBox = svg.getBoundingClientRect();
    svg.querySelectorAll('text').forEach((t, idx) => {
      const box = t.getBoundingClientRect();
      const cs = getComputedStyle(t);
      out.texts.push({
        order: order.get(t), idx,
        text: (t.textContent || '').trim(),
        x: box.x, y: box.y, w: box.width, h: box.height,
        fontSize: parseFloat(cs.fontSize),
        fontFamily: cs.fontFamily,
        opacity: parseFloat(cs.opacity),
        display: cs.display,
        svg: { x: svgBox.x, y: svgBox.y, w: svgBox.width, h: svgBox.height },
      });
    });
    for (const r of svg.querySelectorAll('rect')) {
      const box = r.getBoundingClientRect();
      const cs = getComputedStyle(r);
      out.rects.push({
        order: order.get(r),
        x: box.x, y: box.y, w: box.width, h: box.height,
        fill: cs.fill, fillOpacity: parseFloat(cs.fillOpacity || '1'),
      });
    }
  }
  return out;
}
"""


# CDP reports the resolved *face* ("Pretendard SemiBold", "Geist Medium"), while a CSS stack
# names the *family* ("Pretendard"). Strip style and weight words before comparing, or every
# non-regular weight reads as a substitution.
FACE_SUFFIX_RE = re.compile(
    r"\b(thin|extra ?light|ultra ?light|light|regular|book|normal|text|medium|demi ?bold|"
    r"semi ?bold|bold|extra ?bold|ultra ?bold|heavy|black|italic|oblique|variable|vf|"
    r"condensed|expanded|display|pro|std)\b",
    re.I,
)


def family_key(name: str) -> str:
    """Normalize a font name to its family for comparison."""
    stripped = FACE_SUFFIX_RE.sub(" ", name.replace("-", " ").replace("_", " "))
    return " ".join(stripped.split()).casefold()


def opaque(rect: dict) -> bool:
    fill = (rect.get("fill") or "").replace(" ", "").casefold()
    if fill in {"none", "transparent", "rgba(0,0,0,0)"}:
        return False
    alpha_match = re.match(r"rgba\([^)]*,([\d.]+)\)$", fill)
    alpha = float(alpha_match.group(1)) if alpha_match else 1.0
    return alpha * (rect.get("fillOpacity") or 1.0) > 0.5


def innermost_container(text: dict, rects: list[dict]) -> dict | None:
    cx, cy = text["x"] + text["w"] / 2, text["y"] + text["h"] / 2
    best: dict | None = None
    for rect in rects:
        if rect["w"] <= 0 or rect["h"] <= 0:
            continue
        # A full-bleed background rect contains everything; it is not a container.
        if rect["w"] >= text["svg"]["w"] * 0.95 and rect["h"] >= text["svg"]["h"] * 0.95:
            continue
        if not (rect["x"] <= cx <= rect["x"] + rect["w"] and rect["y"] <= cy <= rect["y"] + rect["h"]):
            continue
        if best is None or rect["w"] * rect["h"] < best["w"] * best["h"]:
            best = rect
    return best


def overlap_area(a: dict, b: dict) -> float:
    dx = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    dy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return dx * dy if dx > 0 and dy > 0 else 0.0


def check_overflow(data: dict, errors: list[str]) -> None:
    for text in data["texts"]:
        label = text["text"]
        if not label or text["w"] <= 0:
            continue
        container = innermost_container(text, data["rects"])
        if container is None:
            continue
        left = container["x"] - text["x"]
        right = (text["x"] + text["w"]) - (container["x"] + container["w"])
        if left > EDGE_TOLERANCE_PX or right > EDGE_TOLERANCE_PX:
            over = max(left, right)
            script = "Hangul" if HANGUL_RE.search(label) else "Latin"
            errors.append(
                f"{script} label {label[:28]!r} renders {text['w']:.0f}px wide and overruns its "
                f"{container['w']:.0f}px box by {over:.0f}px — widen the node to the next ramp "
                "step, split onto a second tspan, or shorten the label"
            )


def check_occlusion(data: dict, errors: list[str]) -> None:
    for text in data["texts"]:
        if not text["text"] or text["w"] <= 0:
            continue
        area = text["w"] * text["h"]
        if area <= 0:
            continue
        for rect in data["rects"]:
            if rect["order"] <= text["order"] or not opaque(rect):
                continue
            if rect["w"] >= text["svg"]["w"] * 0.95:
                continue
            covered = overlap_area(text, rect) / area
            if covered > OCCLUSION_MIN_RATIO:
                errors.append(
                    f"label {text['text'][:28]!r} is {covered * 100:.0f}% covered by a node painted "
                    "after it — paint order is background → zones → arrows → labels → nodes, so move "
                    "the label onto open canvas (SKILL.md §6 rule 6)"
                )
                break


def check_fonts(page, data: dict, errors: list[str], warnings: list[str]) -> None:
    """Report the family the browser actually used, per CDP."""
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send("DOM.enable")
        cdp.send("CSS.enable")
        document = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
        found = cdp.send(
            "DOM.querySelectorAll",
            {"nodeId": document["root"]["nodeId"], "selector": "svg text"},
        )["nodeIds"]
    except Exception as exc:  # noqa: BLE001 — CDP is best-effort, never fatal
        warnings.append(f"could not read platform fonts over CDP ({exc}); skipping the font check")
        return

    texts = data["texts"]
    for index, node_id in enumerate(found):
        if index >= len(texts):
            break
        label = texts[index]["text"]
        if not label:
            continue
        try:
            fonts = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node_id})["fonts"]
        except Exception:  # noqa: BLE001
            continue
        if not fonts:
            continue
        used = ", ".join(f"{f['familyName']} ({f['glyphCount']} glyphs)" for f in fonts)
        declared = {
            family_key(part.strip().strip("'\""))
            for part in (texts[index]["fontFamily"] or "").split(",")
        }
        for font in fonts:
            if family_key(font["familyName"]) in declared:
                continue
            if CJK_RE.search(label):
                errors.append(
                    f"label {label[:24]!r} rendered in {font['familyName']!r}, which is not in its "
                    f"declared stack — the CJK glyphs fell through to a system font. "
                    f"Used: {used}. Add a Korean webfont family to the stack "
                    "(references/ko-typography.md §1) so the file travels."
                )
            else:
                warnings.append(
                    f"label {label[:24]!r} rendered in {font['familyName']!r}, outside its declared "
                    f"stack. Used: {used}."
                )
            break


def check_page_overflow(data: dict, warnings: list[str], viewport_width: int) -> None:
    if data["viewport"]["w"] > viewport_width + 4:
        warnings.append(
            f"the page scrolls horizontally at {viewport_width}px "
            f"(content is {data['viewport']['w']:.0f}px) — the SVG min-width may exceed the frame"
        )


def inspect(path: Path, shot_dir: Path | None, scale: float, width: int, height: int) -> tuple[list[str], list[str]]:
    from playwright.sync_api import sync_playwright

    errors: list[str] = []
    warnings: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
        page.goto(path.resolve().as_uri(), wait_until="load")
        try:
            page.evaluate("() => document.fonts.ready")
            page.wait_for_timeout(400)
        except Exception:  # noqa: BLE001
            pass

        data = page.evaluate(EXTRACT_JS)
        if not data["texts"]:
            warnings.append("no <text> elements found inside an <svg> — nothing to measure")

        check_overflow(data, errors)
        check_occlusion(data, errors)
        check_fonts(page, data, errors, warnings)
        check_page_overflow(data, warnings, width)

        if shot_dir is not None:
            shot_dir.mkdir(parents=True, exist_ok=True)
            target = shot_dir / f"{path.stem}.png"
            page.screenshot(path=str(target), full_page=True)
            print(f"     screenshot → {target}")
        browser.close()
    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a diagram and measure it in a real browser.")
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--shot", type=Path, default=None, metavar="DIR",
                    help="write a full-page PNG per file into DIR")
    ap.add_argument("--scale", type=float, default=2.0, help="device scale factor (default 2)")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = ap.parse_args()

    failed = False
    report: dict[str, dict[str, list[str]]] = {}
    for path in args.paths:
        if not path.is_file():
            print(f"FAIL {path}: not a file", file=sys.stderr)
            failed = True
            continue
        errors, warnings = inspect(path, args.shot, args.scale, args.width, args.height)
        report[str(path)] = {"errors": errors, "warnings": warnings}
        if not args.json:
            for message in errors:
                print(f"FAIL {path}: {message}", file=sys.stderr)
            for message in warnings:
                print(f"WARN {path}: {message}", file=sys.stderr)
            if not errors:
                print(f"OK {path}" + (f" ({len(warnings)} warning(s))" if warnings else ""))
        if errors:
            failed = True

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
