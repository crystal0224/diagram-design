#!/usr/bin/env python3
"""Korean (CJK) checks for a generated diagram HTML file, with no third-party deps.

    python3 <skill-dir>/scripts/ko_check.py my-diagram.html

The shipped skin is calibrated for Latin: its three families carry no Hangul
glyphs, and every width budget in SKILL.md assumes a ~0.5em Latin advance while
a Hangul syllable advances a full 1.0em. This checker enforces the Korean layer
described in references/ko-typography.md:

  * Hangul is never rendered below the 12px floor
  * every Hangul-bearing font stack actually covers Hangul
  * a Hangul label does not overrun the box or mask it sits inside
  * tracking, casing, document language, and CJK line-breaking are set for Korean

Geometry here is *estimated* from character advances, deliberately conservative:
a label is only reported when a rect genuinely contains its anchor point, and
any text under a transformed group is skipped. For ground truth, render the file
and measure it — see references/verify-render.md and scripts/render_check.py.

Exit code 1 on errors; warnings and notes never fail the run.
"""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# --- Korean layer constants (references/ko-typography.md) --------------------

HANGUL_FLOOR_PX = 12.0
MAX_HANGUL_TRACKING_EM = 0.08
KO_LINE_HEIGHT_MIN = 1.55

# Families that actually ship Hangul glyphs. Latin-only families in the default
# skin (Geist, Instrument Serif, Geist Mono) are intentionally absent.
KOREAN_FAMILIES = {
    "pretendard",
    "pretendard variable",
    "ibm plex sans kr",
    "noto sans kr",
    "noto serif kr",
    "nanum gothic",
    "nanum myeongjo",
    "gowun batang",
    "gowun dodum",
    "gothic a1",
    "spoqa han sans neo",
    "apple sd gothic neo",
    "malgun gothic",
    "맑은 고딕",
}
# Generic families resolve to *something* with Hangul on most systems, but not to
# anything you laid the box out for. Accepted only as a trailing fallback.
GENERIC_FAMILIES = {"sans-serif", "serif", "monospace", "system-ui", "ui-monospace", "ui-sans-serif"}

HANGUL_RE = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
CJK_WIDE_RE = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏一-鿿぀-ヿ！-｠　-〿]")
DEFAULT_FONT_SIZE = 12.0
NARROW_LATIN = set("iljtfr.,;:!|'’()[]")

# Wording patterns that read as report prose rather than a diagram label.
STIFF_PATTERNS = [
    (re.compile(r"에\s*대한"), "에 대한"),
    (re.compile(r"에\s*있어서"), "에 있어서"),
    (re.compile(r"를?\s*수행(함|한다|하는)"), "~를 수행함"),
    (re.compile(r"[가-힣]다\.$"), "종결형 문장"),
    (re.compile(r"[가-힣][.。]$"), "말미 마침표"),
]


def is_hangul(text: str) -> bool:
    return bool(HANGUL_RE.search(text))


def hangul_ratio(text: str) -> float:
    letters = [c for c in text if not c.isspace()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if HANGUL_RE.match(c)) / len(letters)


def advance_em(ch: str) -> float:
    """Approximate advance width in em for one character."""
    if CJK_WIDE_RE.match(ch):
        return 1.0
    if ch == " ":
        return 0.28
    if ch in NARROW_LATIN:
        return 0.30
    if ch.isdigit():
        return 0.56
    if "A" <= ch <= "Z":
        return 0.66
    if "a" <= ch <= "z":
        return 0.53
    return 0.55


def text_width(text: str, font_size: float, tracking_em: float = 0.0) -> float:
    return sum(advance_em(c) + tracking_em for c in text) * font_size


def parse_length(value: str | None, default: float | None = None) -> float | None:
    if value is None:
        return default
    match = re.match(r"\s*(-?[\d.]+)\s*(px|pt|rem|em)?\s*$", value)
    if not match:
        return default
    number = float(match.group(1))
    unit = match.group(2) or "px"
    if unit == "pt":
        return number * 4 / 3
    if unit in {"rem", "em"}:
        return number * 16
    return number


def parse_tracking_em(value: str | None, font_size: float) -> float:
    if not value:
        return 0.0
    match = re.match(r"\s*(-?[\d.]+)\s*(em|px|rem)?\s*$", value)
    if not match:
        return 0.0
    number = float(match.group(1))
    unit = match.group(2) or "px"
    if unit == "em":
        return number
    if unit == "rem":
        return number * 16 / font_size if font_size else 0.0
    return number / font_size if font_size else 0.0


def families(font_family: str | None) -> list[str]:
    if not font_family:
        return []
    return [part.strip().strip("'\"").casefold() for part in font_family.split(",") if part.strip()]


def style_decl(style: str | None, prop: str) -> str | None:
    if not style:
        return None
    for chunk in style.split(";"):
        if ":" not in chunk:
            continue
        key, _, value = chunk.partition(":")
        if key.strip().casefold() == prop:
            return value.strip()
    return None


# --- document model ---------------------------------------------------------


class Node:
    __slots__ = (
        "tag",
        "attrs",
        "text",
        "order",
        "in_svg",
        "svg_scope",
        "transformed",
        "classes",
        "inherited",
    )

    def __init__(self, tag: str, attrs: dict[str, str], order: int, in_svg: bool, transformed: bool,
                 inherited: dict[str, str], svg_scope: int | None = None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.text = ""
        self.order = order
        self.in_svg = in_svg
        self.svg_scope = svg_scope
        self.transformed = transformed
        self.classes = [c for c in (attrs.get("class") or "").split() if c]
        self.inherited = inherited


class DiagramParser(HTMLParser):
    """Collects <text>/<rect> geometry, style rules, and the document language."""

    INHERITABLE = ("font-size", "font-family", "letter-spacing", "text-anchor")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.texts: list[Node] = []
        self.rects: list[Node] = []
        self.html_blocks: list[Node] = []
        self.styles: list[str] = []
        self.links: list[str] = []
        self.lang: str | None = None
        self._order = 0
        self._svg_depth = 0
        self._svg_serial = 0
        self._svg_scopes: list[int] = []
        self._transform_depth = 0
        self._stack: list[tuple[str, bool, dict[str, str]]] = []
        self._capture: Node | None = None
        self._in_style = False

    def _inherited(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for _, _, ctx in self._stack:
            merged.update(ctx)
        return merged

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        data = {k.casefold(): (v or "") for k, v in attrs}
        self._order += 1

        if tag == "html" and "lang" in data:
            self.lang = data["lang"]
        if tag == "link" and "stylesheet" in (data.get("rel", "").casefold()):
            self.links.append(data.get("href", ""))
        if tag == "style":
            self._in_style = True
            self.styles.append("")
            return

        had_transform = bool(data.get("transform"))
        if had_transform:
            self._transform_depth += 1

        ctx = {key: data[key] for key in self.INHERITABLE if key in data}
        style = data.get("style")
        if style:
            for key in self.INHERITABLE:
                value = style_decl(style, key)
                if value:
                    ctx[key] = value

        if tag == "svg":
            self._svg_serial += 1
            self._svg_scopes.append(self._svg_serial)
            self._svg_depth += 1

        node = Node(
            tag,
            data,
            self._order,
            self._svg_depth > 0,
            self._transform_depth > 0,
            self._inherited(),
            self._svg_scopes[-1] if self._svg_scopes else None,
        )

        if tag == "rect" and self._svg_depth > 0:
            self.rects.append(node)
        elif tag == "text" and self._svg_depth > 0:
            self.texts.append(node)
            self._capture = node
        elif tag in {"p", "h1", "h2", "h3", "li", "td", "th", "div", "span", "figcaption"} and self._svg_depth == 0:
            self.html_blocks.append(node)
            if self._capture is None:
                self._capture = node

        self._stack.append((tag, had_transform, ctx))

        if tag in {"br", "img", "link", "meta", "input", "hr", "use", "path", "line", "circle",
                   "polygon", "polyline", "ellipse", "marker", "stop"}:
            self._pop(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self._pop(tag.casefold())

    def handle_endtag(self, tag: str) -> None:
        self._pop(tag.casefold())

    def _pop(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False
            return
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                _, had_transform, _ = self._stack.pop(index)
                if had_transform:
                    self._transform_depth = max(0, self._transform_depth - 1)
                break
        if tag == "svg":
            self._svg_depth = max(0, self._svg_depth - 1)
            if self._svg_scopes:
                self._svg_scopes.pop()
        if self._capture is not None and self._capture.tag == tag:
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._in_style and self.styles:
            self.styles[-1] += data
            return
        if self._capture is not None:
            self._capture.text += data


def css_rules(styles: list[str]) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    body = "\n".join(styles)
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", body):
        rules.append((match.group(1).strip(), match.group(2)))
    return rules


def selector_matches(selector: str, node: Node) -> bool:
    """Match the rightmost compound token of a selector — `text`, `.eyebrow`, `svg text.mono`."""
    parts = selector.strip().split()
    if not parts:
        return False
    token = parts[-1].split(":")[0]
    tag, *classes = token.split(".")
    if tag and tag.casefold() != node.tag:
        return False
    if not tag and not classes:
        return False
    return all(cls in node.classes for cls in classes)


def declarations_for(node: Node, rules: list[tuple[str, str]], prop: str) -> list[str]:
    found: list[str] = []
    for selector, block in rules:
        value = style_decl(block, prop)
        if value is None:
            continue
        if any(selector_matches(part, node) for part in selector.split(",")):
            found.append(value)
    return found


def root_variables(rules: list[tuple[str, str]]) -> dict[str, str]:
    variables: dict[str, str] = {}
    for selector, block in rules:
        if ":root" not in selector and "html" not in selector.casefold():
            continue
        for chunk in block.split(";"):
            key, _, value = chunk.partition(":")
            key = key.strip()
            if key.startswith("--"):
                variables[key] = value.strip()
    return variables


def expand_vars(value: str | None, variables: dict[str, str], depth: int = 0) -> str | None:
    """Resolve `var(--x)` / `var(--x, fallback)` against :root, one level at a time."""
    if value is None or "var(" not in value or depth > 4:
        return value

    def substitute(match: re.Match[str]) -> str:
        inner = match.group(1)
        name, _, fallback = inner.partition(",")
        return variables.get(name.strip(), fallback.strip())

    return expand_vars(re.sub(r"var\(([^()]*)\)", substitute, value), variables, depth + 1)


def effective(node: Node, key: str, rules: list[tuple[str, str]], variables: dict[str, str],
              default: str | None = None) -> str | None:
    """CSS cascade, simplified: inline style → presentation attribute → stylesheet → inherited."""
    value = style_decl(node.attrs.get("style"), key)
    if value is None and key in node.attrs:
        value = node.attrs[key]
    if value is None:
        declarations = declarations_for(node, rules, key)
        value = declarations[-1] if declarations else None
    if value is None:
        value = node.inherited.get(key, default)
    return expand_vars(value, variables)


class Style:
    """Resolves a property for a node against the document's stylesheet and variables."""

    def __init__(self, rules: list[tuple[str, str]], variables: dict[str, str]) -> None:
        self.rules = rules
        self.variables = variables

    def get(self, node: Node, key: str, default: str | None = None) -> str | None:
        return effective(node, key, self.rules, self.variables, default)


# --- checks -----------------------------------------------------------------


def check_font_coverage(parser: DiagramParser, style: Style, errors: list[str], warnings: list[str]) -> None:
    korean_link = any(
        any(fam.replace(" ", "+") in href.replace("%20", "+") for fam in ("IBM+Plex+Sans+KR", "Noto+Sans+KR", "Noto+Serif+KR", "Nanum", "Gowun", "Gothic+A1"))
        for href in parser.links
    )
    hangul_present = any(is_hangul(node.text) for node in parser.texts + parser.html_blocks)
    if hangul_present and not korean_link:
        errors.append(
            "the document has Hangul but no Korean family in the Google Fonts link — "
            "add IBM+Plex+Sans+KR (and Noto+Serif+KR for the title); "
            "see references/ko-typography.md §1"
        )

    for node in parser.texts:
        if not is_hangul(node.text):
            continue
        stack = families(style.get(node, "font-family"))
        if not stack:
            errors.append(
                f"<text> with Hangul declares no font-family (text: {node.text.strip()[:24]!r}); "
                "SVG text does not inherit the CSS variables — name the stack explicitly"
            )
            continue
        covering = [f for f in stack if f in KOREAN_FAMILIES]
        if not covering:
            trailing_generic = stack[-1] in GENERIC_FAMILIES
            detail = (
                "falls through to the generic family, which resolves to a different skeleton and a "
                "different advance width than the layout assumes"
                if trailing_generic
                else "has no family that ships Hangul glyphs — this renders as tofu"
            )
            errors.append(
                f"Hangul <text> font stack {stack} {detail} "
                f"(text: {node.text.strip()[:24]!r})"
            )


def check_size_floor(parser: DiagramParser, style: Style, errors: list[str]) -> None:
    for node in parser.texts:
        if not is_hangul(node.text):
            continue
        size = parse_length(style.get(node, "font-size"), DEFAULT_FONT_SIZE) or DEFAULT_FONT_SIZE
        if size < HANGUL_FLOOR_PX:
            errors.append(
                f"Hangul at {size:g}px is below the {HANGUL_FLOOR_PX:g}px floor "
                f"(text: {node.text.strip()[:24]!r}) — grow the node, never the floor; "
                "ko-typography.md §2"
            )


def check_tracking_and_case(parser: DiagramParser, style: Style, rules: list[tuple[str, str]], warnings: list[str]) -> None:
    for node in parser.texts:
        if not is_hangul(node.text):
            continue
        size = parse_length(style.get(node, "font-size"), DEFAULT_FONT_SIZE) or DEFAULT_FONT_SIZE
        tracking = parse_tracking_em(style.get(node, "letter-spacing"), size)
        if tracking > MAX_HANGUL_TRACKING_EM:
            warnings.append(
                f"letter-spacing {tracking:.2f}em on Hangul (text: {node.text.strip()[:20]!r}) — "
                f"above {MAX_HANGUL_TRACKING_EM}em the syllables read as broken spacing"
            )

    for node in parser.html_blocks:
        if not is_hangul(node.text):
            continue
        size = parse_length(style.get(node, "font-size"), 16.0) or 16.0
        for value in declarations_for(node, rules, "letter-spacing"):
            if parse_tracking_em(value, size) > MAX_HANGUL_TRACKING_EM:
                warnings.append(
                    f"<{node.tag} class={' '.join(node.classes) or '-'}> carries Hangul with "
                    f"letter-spacing {value.strip()} — drop to 0.02–0.06em for Korean"
                )
        for value in declarations_for(node, rules, "text-transform"):
            if value.strip().casefold() == "uppercase":
                warnings.append(
                    f"<{node.tag} class={' '.join(node.classes) or '-'}> carries Hangul with "
                    "text-transform: uppercase — a no-op on Hangul that still uppercases any "
                    "mixed-in Latin (데이터 PIPELINE)"
                )


def check_line_breaking(parser: DiagramParser, rules: list[tuple[str, str]], warnings: list[str]) -> None:
    korean_prose = [n for n in parser.html_blocks if is_hangul(n.text) and len(n.text.strip()) >= 12]
    if not korean_prose:
        return
    all_css = " ".join(block for _, block in rules)
    if "keep-all" not in all_css:
        warnings.append(
            "Korean prose in HTML text blocks but no `word-break: keep-all` in the stylesheet — "
            "the browser will break Korean lines mid-word; add keep-all plus "
            "overflow-wrap: break-word (ko-typography.md §3)"
        )
    for node in korean_prose:
        for value in declarations_for(node, rules, "line-height"):
            height = parse_length(value, None)
            numeric = height / 16 if height and height > 3 else (float(value) if re.match(r"^\s*[\d.]+\s*$", value) else None)
            if numeric is not None and numeric < KO_LINE_HEIGHT_MIN:
                warnings.append(
                    f"<{node.tag} class={' '.join(node.classes) or '-'}> Korean prose at "
                    f"line-height {value.strip()} reads cramped — Hangul wants ≥{KO_LINE_HEIGHT_MIN}"
                )
                break


def check_lang(parser: DiagramParser, warnings: list[str]) -> None:
    corpus = " ".join(n.text for n in parser.texts + parser.html_blocks)
    if hangul_ratio(corpus) < 0.3:
        return
    lang = (parser.lang or "").casefold()
    if not lang.startswith("ko"):
        warnings.append(
            f"document is predominantly Korean but <html lang=\"{parser.lang or ''}\"> — set lang=\"ko\" "
            "so shared CJK codepoints pick Korean glyph forms and screen readers use the right voice"
        )


def enclosing_rect(node: Node, rects: list[Node]) -> tuple[Node, float, float, float, float] | None:
    tx = parse_length(node.attrs.get("x"), None)
    ty = parse_length(node.attrs.get("y"), None)
    if tx is None or ty is None:
        return None
    best: tuple[Node, float, float, float, float] | None = None
    for rect in rects:
        if rect.svg_scope != node.svg_scope:
            continue
        if rect.transformed:
            continue
        rx = parse_length(rect.attrs.get("x"), None)
        ry = parse_length(rect.attrs.get("y"), None)
        rw = parse_length(rect.attrs.get("width"), None)
        rh = parse_length(rect.attrs.get("height"), None)
        if None in (rx, ry, rw, rh) or rw <= 0 or rh <= 0:
            continue
        if not (rx <= tx <= rx + rw and ry <= ty <= ry + rh):
            continue
        if best is None or rw * rh < best[3] * best[4]:
            best = (rect, rx, ry, rw, rh)
    return best


def check_overflow(parser: DiagramParser, style: Style, errors: list[str]) -> None:
    for node in parser.texts:
        label = node.text.strip()
        if not label or not is_hangul(label):
            continue
        if node.transformed:
            continue
        found = enclosing_rect(node, parser.rects)
        if found is None:
            continue
        _, rx, _, rw, rh = found
        size = parse_length(style.get(node, "font-size"), DEFAULT_FONT_SIZE) or DEFAULT_FONT_SIZE
        tracking = parse_tracking_em(style.get(node, "letter-spacing"), size)
        width = text_width(label, size, tracking)
        anchor = (style.get(node, "text-anchor") or "start").strip().casefold()
        tx = parse_length(node.attrs.get("x"), 0.0) or 0.0
        if anchor == "middle":
            x0 = tx - width / 2
        elif anchor == "end":
            x0 = tx - width
        else:
            x0 = tx
        x1 = x0 + width
        margin = 2.0 if rh <= 16 else 4.0
        if x0 < rx + margin - 0.5 or x1 > rx + rw - margin + 0.5:
            kind = "mask" if rh <= 16 else "box"
            syllables = len(HANGUL_RE.findall(label))
            fits = max(0, int((rw - 2 * margin) // size))
            errors.append(
                f"Hangul label {label[:20]!r} needs ~{width:.0f}px at {size:g}px but its {kind} is "
                f"{rw:g}px wide (fits ~{fits} syllables, label has {syllables}) — "
                + (
                    "size the mask as syllables x font-size + 8 and re-center"
                    if kind == "mask"
                    else "widen the node to the next ramp step or split onto a second tspan"
                )
            )


def check_wording(parser: DiagramParser, notes: list[str]) -> None:
    seen: set[str] = set()
    for node in parser.texts:
        label = node.text.strip()
        if not label or not is_hangul(label) or label in seen:
            continue
        seen.add(label)
        for pattern, name in STIFF_PATTERNS:
            if pattern.search(label):
                notes.append(
                    f"label {label[:24]!r} reads as report prose ({name}) — diagram labels are "
                    "noun phrases without particles or terminal punctuation (ko-typography.md §4)"
                )
                break


def verify(path: Path) -> tuple[list[str], list[str], list[str]]:
    source = path.read_text(encoding="utf-8")
    parser = DiagramParser()
    parser.feed(source)
    parser.close()
    rules = css_rules(parser.styles)

    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    if not any(is_hangul(n.text) for n in parser.texts + parser.html_blocks):
        return errors, warnings, ["no Hangul in this document — the Korean layer does not apply"]

    style = Style(rules, root_variables(rules))
    check_font_coverage(parser, style, errors, warnings)
    check_size_floor(parser, style, errors)
    check_overflow(parser, style, errors)
    check_tracking_and_case(parser, style, rules, warnings)
    check_line_breaking(parser, rules, warnings)
    check_lang(parser, warnings)
    check_wording(parser, notes)
    return errors, warnings, notes


def main() -> int:
    ap = argparse.ArgumentParser(description="Korean typography + geometry checks for a diagram HTML file.")
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures too")
    args = ap.parse_args()

    failed = False
    for path in args.paths:
        if not path.is_file():
            print(f"FAIL {path}: not a file", file=sys.stderr)
            failed = True
            continue
        errors, warnings, notes = verify(path)
        for message in errors:
            print(f"FAIL {path}: {message}", file=sys.stderr)
        for message in warnings:
            print(f"WARN {path}: {message}", file=sys.stderr)
        for message in notes:
            print(f"NOTE {path}: {message}")
        if errors or (args.strict and warnings):
            failed = True
        else:
            print(f"OK {path}" + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
