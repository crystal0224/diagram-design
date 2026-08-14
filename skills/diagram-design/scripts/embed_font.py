#!/usr/bin/env python3
"""Subset a locally installed font to the glyphs a diagram actually uses, and inline it.

    python3 <skill-dir>/scripts/embed_font.py diagram.html
    python3 <skill-dir>/scripts/embed_font.py diagram.html --family "Noto Sans KR"
    python3 <skill-dir>/scripts/embed_font.py diagram.html --check

Why this exists: Pretendard is the best Hangul companion to Geist, and it is not
on Google Fonts. Naming it in the CSS stack works on a machine that has it
installed and silently degrades everywhere else — the file looks perfect locally
right up until you send it (see references/verify-render.md).

A diagram is not a web page. It carries a few dozen distinct characters, so the
whole objection to embedding CJK — megabytes of glyphs — does not apply once the
font is subset to the text actually present. In practice a Korean diagram costs
2–6 KB per weight, against a 1.5 MB source.

The result stays a single self-contained file with no remote dependency, which
is the same contract the rest of the skill holds to. Re-running is idempotent:
an existing embedded block is replaced, not stacked. Re-run after editing labels,
or the new characters will be missing from the subset — `--check` reports exactly
that without modifying the file.

Requires fonttools with brotli (`pip install "fonttools[woff]" brotli`).

Licensing: embedding is redistribution. Pretendard is OFL-1.1, which permits it.
Confirm the license before pointing --family at a commercial font.
"""

from __future__ import annotations

import argparse
import base64
import io
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import tempfile
from html.parser import HTMLParser
from pathlib import Path

FONT_DIRS = [
    Path.home() / "Library" / "Fonts",
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path.home() / ".fonts",
    Path("/usr/share/fonts"),
]

# CSS numeric weight → the style word font files use in their filename.
WEIGHT_NAMES = {
    100: ("Thin",), 200: ("ExtraLight", "UltraLight"), 300: ("Light",),
    400: ("Regular", "Normal"), 500: ("Medium",), 600: ("SemiBold", "DemiBold"),
    700: ("Bold",), 800: ("ExtraBold", "UltraBold"), 900: ("Black", "Heavy"),
}

BEGIN = "/* embed_font.py: begin embedded subset — regenerate, do not hand-edit */"
END = "/* embed_font.py: end embedded subset */"
BLOCK_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)

G_BEGIN = "/* embed_font.py: begin inlined webfonts — regenerate, do not hand-edit */"
G_END = "/* embed_font.py: end inlined webfonts */"
G_BLOCK_RE = re.compile(re.escape(G_BEGIN) + r".*?" + re.escape(G_END), re.S)
GOOGLE_LINK_RE = re.compile(
    r"[ \t]*<link[^>]+href=[\"\'](https://fonts\.googleapis\.com/css2[^\"\']*)[\"\'][^>]*>\n?", re.I)
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# Families that actually carry CJK glyphs. Everything else gets a Latin-only
# `text=`, so its unicode-range never claims Hangul it cannot draw — a face that
# claims a codepoint and lacks the glyph renders tofu instead of falling through.
CJK_WEBFONTS = {"ibm plex sans kr", "noto sans kr", "noto serif kr", "nanum gothic",
                "nanum myeongjo", "gowun batang", "gowun dodum", "gothic a1"}

CJK_RE = re.compile(r"[가-힣ᄀ-ᇿ一-鿿぀-ヿ]")

# Characters every diagram needs regardless of its labels.
ALWAYS = set(" ·—–-…()[]{}/:.,%0123456789")


class TextHarvester(HTMLParser):
    """Every character that will be painted — not the markup around it."""

    # Elements whose text content is never rendered as glyphs. Void elements must
    # NOT appear here: they have no end tag, so counting them would leave the skip
    # depth stuck above zero and silently swallow the entire rest of the document.
    SKIP = {"script", "style", "title", "desc"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr", "path", "line", "circle",
            "rect", "polygon", "polyline", "ellipse", "use", "stop", "image"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chars: set[str] = set()
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in self.SKIP and tag not in self.VOID:
            self._skip_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return  # <foo /> opens and closes at once; it can hold no text

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.chars.update(data)


def used_characters(source: str) -> set[str]:
    harvester = TextHarvester()
    harvester.feed(source)
    harvester.close()
    chars = {c for c in harvester.chars if c.isprintable() and not c.isspace()}
    return chars | ALWAYS


def used_weights(source: str) -> set[int]:
    """Which numeric weights the document asks for, normalized onto the ramp."""
    weights: set[int] = {400}
    for match in re.finditer(r"font-weight\s*[:=]\s*[\"']?\s*(\d{3}|bold|normal)", source, re.I):
        token = match.group(1).lower()
        if token == "bold":
            weights.add(700)
        elif token == "normal":
            weights.add(400)
        else:
            weights.add(int(token))
    return {w for w in weights if w in WEIGHT_NAMES}


def find_font_file(family: str, weight: int) -> Path | None:
    slug = family.replace(" ", "").casefold()
    for directory in FONT_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*")):
            if path.suffix.lower() not in {".otf", ".ttf", ".woff2", ".ttc"}:
                continue
            stem = path.stem.replace(" ", "").replace("-", "").replace("_", "").casefold()
            if not stem.startswith(slug):
                continue
            style = stem[len(slug):]
            if "italic" in style or "oblique" in style:
                continue
            for name in WEIGHT_NAMES[weight]:
                candidate = name.replace(" ", "").casefold()
                # "Regular" is also the bare, suffix-less file.
                if style == candidate or (weight == 400 and style == ""):
                    return path
    return None


def subset(font: Path, characters: set[str]) -> bytes:
    text = "".join(sorted(characters))
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "subset.woff2"
        result = subprocess.run(
            [sys.executable, "-m", "fontTools.subset", str(font),
             f"--text={text}", "--flavor=woff2", f"--output-file={output}",
             # Default layout features only. Keeping all of them costs ~33% more
             # for shaping a diagram label will never need — precomposed Hangul
             # syllables and Latin node names require no complex substitution.
             "--no-hinting", "--desubroutinize"],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not output.is_file():
            raise RuntimeError(f"pyftsubset failed on {font.name}: {result.stderr.strip()[:300]}")
        return output.read_bytes()


def uncovered_characters(block: str, characters: set[str]) -> set[str]:
    """Characters the document paints that the embedded faces cannot render."""
    from fontTools.ttLib import TTFont  # local import: only --check needs it

    payloads = re.findall(r"base64,([A-Za-z0-9+/=]+)\)", block)
    if not payloads:
        return set(characters)
    covered: set[int] = set()
    for payload in payloads:
        try:
            font = TTFont(io.BytesIO(base64.b64decode(payload)), fontNumber=0)
            for table in font["cmap"].tables:
                covered.update(table.cmap.keys())
        except Exception:  # noqa: BLE001 — an unreadable face proves nothing is covered
            continue
    return {c for c in characters if ord(c) not in covered}


def parse_google_link(href: str) -> list[tuple[str, list[int]]]:
    """`...css2?family=Geist:wght@400;500&family=Instrument+Serif:ital@0;1` → [(family, weights)]."""
    families: list[tuple[str, list[int]]] = []
    for spec in re.findall(r"family=([^&]+)", href):
        spec = urllib.parse.unquote(spec).replace("+", " ")
        name, _, axes = spec.partition(":")
        weights = [int(w) for w in re.findall(r"\b([1-9]00)\b", axes)] or [400]
        families.append((name.strip(), sorted(set(weights))))
    return families


def fetch_google_subset(family: str, weight: int, characters: set[str]) -> bytes | None:
    """One already-subset woff2 from the Google Fonts `text=` API."""
    if not characters:
        return None
    text = "".join(sorted(characters))
    url = (f"https://fonts.googleapis.com/css2?family={urllib.parse.quote(family.replace(' ', '+'), safe='+')}"
           f":wght@{weight}&text={urllib.parse.quote(text)}")
    try:
        css = urllib.request.urlopen(  # noqa: S310 — pinned host
            urllib.request.Request(url, headers={"User-Agent": BROWSER_UA}), timeout=30
        ).read().decode("utf-8")
    except Exception:  # noqa: BLE001 — a family without this weight is not fatal
        return None
    match = re.search(r"src:\s*url\((https://fonts\.gstatic\.com/[^)]+)\)", css)
    if not match:
        return None
    try:
        return urllib.request.urlopen(  # noqa: S310 — pinned host
            urllib.request.Request(match.group(1), headers={"User-Agent": BROWSER_UA}), timeout=30
        ).read()
    except Exception:  # noqa: BLE001
        return None


def inline_google_fonts(source: str, characters: set[str], embedded_family: str | None) -> tuple[str, list[str]]:
    """Replace the Google Fonts <link> with inlined, document-subset faces."""
    link = GOOGLE_LINK_RE.search(source)
    if not link:
        return source, []
    latin_only = {c for c in characters if not CJK_RE.match(c)}
    notes: list[str] = []
    faces: list[str] = []
    for family, weights in parse_google_link(link.group(1)):
        is_cjk = family.casefold() in CJK_WEBFONTS
        if is_cjk and embedded_family:
            # A locally embedded Hangul face already covers this; a second one is dead weight.
            notes.append(f"skipped {family} — {embedded_family} is embedded and covers Hangul")
            continue
        wanted = characters if is_cjk else latin_only
        for weight in weights:
            payload = fetch_google_subset(family, weight, wanted)
            if payload is None:
                notes.append(f"{family} {weight}: no subset returned")
                continue
            encoded = base64.b64encode(payload).decode("ascii")
            faces.append(
                f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};"
                f"font-display:swap;src:url(data:font/woff2;base64,{encoded}) format('woff2');}}"
            )
            notes.append(f"{family} {weight}: {len(payload) / 1024:.1f} KB")
    if not faces:
        return source, notes
    block = "\n".join([G_BEGIN, *faces, G_END])
    source = GOOGLE_LINK_RE.sub("", source, count=1)
    source = G_BLOCK_RE.sub("", source)
    marker = source.find("<style>")
    if marker == -1:
        return source, notes + ["no <style> block to inject into"]
    insert = marker + len("<style>")
    return source[:insert] + "\n" + block + "\n" + source[insert:], notes


def build_block(family: str, faces: list[tuple[int, bytes]]) -> str:
    lines = [BEGIN]
    for weight, payload in sorted(faces):
        encoded = base64.b64encode(payload).decode("ascii")
        lines.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};"
            f"font-display:swap;src:url(data:font/woff2;base64,{encoded}) format('woff2');}}"
        )
    lines.append(END)
    return "\n".join(lines)


def ensure_stack(source: str, family: str) -> tuple[str, list[str]]:
    """Put the embedded family right after the Latin face in every font variable.

    `--font-mono` needs it as much as `--font-sans` does: mono is for technical
    Latin strings, but a legend or eyebrow written in Hangul lands in that stack
    too, and Geist Mono has no Hangul. Without this the label silently resolves
    to a system font — which is the exact failure embedding was meant to end.
    """
    changed: list[str] = []
    for variable in ("--font-sans", "--font-serif", "--font-mono"):
        match = re.search(rf"({re.escape(variable)}:\s*)([^;]+);", source)
        if not match:
            continue
        stack = match.group(2)
        names = [part.strip().strip("'\"") for part in stack.split(",")]
        if family in names:
            continue
        parts = [part.strip() for part in stack.split(",")]
        parts.insert(1, f"'{family}'")
        source = source[:match.start(2)] + ", ".join(parts) + source[match.end(2):]
        changed.append(variable)
    return source, changed


def process(path: Path, family: str, check_only: bool) -> int:
    source = path.read_text(encoding="utf-8")
    characters = used_characters(source)
    weights = used_weights(source)

    existing = BLOCK_RE.search(source)
    if check_only:
        if not existing:
            print(f"MISS {path}: no embedded subset — '{family}' resolves only on machines that "
                  "have it installed", file=sys.stderr)
            return 1
        # The real trap is a *stale* subset: labels edited after embedding render
        # in the fallback while every other gate stays green. So don't just report
        # that a block exists — decode it and compare its cmap against the text.
        missing_glyphs = uncovered_characters(existing.group(0), characters)
        if missing_glyphs:
            shown = "".join(sorted(missing_glyphs))[:40]
            print(f"FAIL {path}: embedded subset is stale — {len(missing_glyphs)} character(s) in "
                  f"the document are not in it ({shown!r}). These render in the fallback font. "
                  "Re-run without --check.", file=sys.stderr)
            return 1
        print(f"OK {path}: embedded subset covers all {len(characters)} distinct characters")
        return 0

    faces: list[tuple[int, bytes]] = []
    missing: list[int] = []
    for weight in sorted(weights):
        font = find_font_file(family, weight)
        if font is None:
            missing.append(weight)
            continue
        faces.append((weight, subset(font, characters)))

    if not faces:
        print(f"FAIL no installed file found for {family!r} at weight(s) {sorted(weights)}. "
              f"Searched: {', '.join(str(d) for d in FONT_DIRS if d.is_dir())}", file=sys.stderr)
        return 1
    for weight in missing:
        print(f"WARN {family} {weight} is not installed — that weight will fall back", file=sys.stderr)

    block = build_block(family, faces)
    if existing:
        source = BLOCK_RE.sub(lambda _: block, source, count=1)
    else:
        marker = source.find("<style>")
        if marker == -1:
            print("FAIL no <style> block to inject into", file=sys.stderr)
            return 1
        insert = marker + len("<style>")
        source = source[:insert] + "\n" + block + "\n" + source[insert:]

    source, changed = ensure_stack(source, family)
    before = len(path.read_text(encoding="utf-8").encode())
    path.write_text(source, encoding="utf-8")
    after = len(source.encode())

    detail = ", ".join(f"{w} ({len(p) / 1024:.1f} KB)" for w, p in sorted(faces))
    print(f"OK {path}")
    print(f"     embedded {family}: {detail}")
    print(f"     {len(characters)} distinct characters · file {before / 1024:.0f} KB → {after / 1024:.0f} KB")
    if changed:
        print(f"     added '{family}' to {', '.join(changed)}")
    print("     re-run after editing labels — new characters are not in this subset")
    return 0


def inline_webfonts(path: Path, embedded_family: str | None) -> int:
    source = path.read_text(encoding="utf-8")
    before = len(source.encode())
    source, notes = inline_google_fonts(source, used_characters(source), embedded_family)
    if not notes:
        print(f"     no Google Fonts link found in {path.name} — nothing to inline")
        return 0
    path.write_text(source, encoding="utf-8")
    after = len(source.encode())
    print(f"     inlined webfonts · file {before / 1024:.0f} KB → {after / 1024:.0f} KB")
    for note in notes:
        print(f"       {note}")
    print("     the Google Fonts <link> is gone — this file needs no network at all")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Subset an installed font to a diagram's text and inline it.")
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--family", default="Pretendard", help="installed family name (default: Pretendard)")
    ap.add_argument("--check", action="store_true", help="report whether a subset is embedded; change nothing")
    ap.add_argument("--google-auto", action="store_true",
                    help="also inline the document's Google Fonts link as subset faces, then remove the link "
                         "(makes the file render identically with no network at all)")
    args = ap.parse_args()

    status = 0
    for path in args.paths:
        if not path.is_file():
            print(f"FAIL {path}: not a file", file=sys.stderr)
            status = 1
            continue
        status |= process(path, args.family, args.check)
        if args.google_auto and not args.check:
            status |= inline_webfonts(path, args.family)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
