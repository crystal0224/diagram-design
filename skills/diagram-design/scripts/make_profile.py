#!/usr/bin/env python3
"""Build a named client profile from a design-md brand, Korean-ready.

    python3 <skill-dir>/scripts/make_profile.py montage --name "Wanted / 원티드"
    python3 <skill-dir>/scripts/make_profile.py linear.app --slug linear --korean
    python3 <skill-dir>/scripts/make_profile.py --seed-default
    python3 <skill-dir>/scripts/make_profile.py montage --dry-run

Composes the two halves that already exist:

  * `design_md_skin.py` resolves a brand's tokens onto the semantic roles and
    measures the result (contrast, one-accent, non-white paper).
  * `references/profiles.md` defines where a saved style guide lives and the
    header it carries, so brand skins survive plugin updates.

This writes the profile file — the full body of `style-guide.md` with the brand's
values substituted in, plus one profile header — into
`~/.diagram-design/profiles/<slug>.md`. Loading it is the skill's `load` verb;
this script never touches the installed working copy.

`--korean` also swaps the typography section for the ko-typography.md stack, so a
Korean project inherits the brand *and* Hangul coverage in one load. Overrides the
role mapping gets wrong are passed with `--set role=hex`, repeatable — the skin
tool's own output labels itself proposed-not-decided for exactly this reason.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
STYLE_GUIDE = SKILL_DIR / "references" / "style-guide.md"
SKIN_TOOL = Path(__file__).resolve().parent / "design_md_skin.py"
LIBRARY = Path.home() / ".diagram-design" / "profiles"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
HEADER_RE = re.compile(r"\A<!-- diagram-design-profile\b.*?-->\n?\n?", re.S)

ROLES = ["paper", "paper-2", "ink", "muted", "soft", "rule", "rule-solid",
         "accent", "accent-tint", "link"]

KOREAN_TYPOGRAPHY = """## Typography

| Role | Family | Size | Weight | Usage |
|---|---|---|---|---|
| `title` | Instrument Serif → Noto Serif KR | 1.75rem | 400 | Page H1 |
| `node-name` | Geist → Pretendard / IBM Plex Sans KR | 12px | 600 | Human-readable labels |
| `sublabel` | Geist Mono (Latin) · sans 12px (Hangul) | 9px / **12px** | 400 | Port, protocol, URL, field type |
| `eyebrow` | Geist Mono | 7–8px / **12px** | 500, tracked 0.04em, no uppercase | Type tags, axis labels |
| `arrow-label` | Geist Mono | 8px / **12px** | 400 | Arrow annotations |
| `callout` | Instrument Serif *italic* | 14px | 400 | Editorial asides only |

**Hangul never below 12px.** The 7–9px Latin steps do not survive translation; 12px is the next value
on the 4px ramp, so the grid rule holds without exception. Tracking above 0.06em breaks Hangul
syllable spacing, and `text-transform: uppercase` is a no-op on Hangul that still uppercases any
mixed-in Latin.

### Font stack

```html
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&family=IBM+Plex+Sans+KR:wght@400;500;600&family=Noto+Serif+KR:wght@400;500&display=swap" rel="stylesheet">
```

```css
--font-sans:  'Geist', 'Pretendard Variable', Pretendard, 'IBM Plex Sans KR', system-ui, sans-serif;
--font-serif: 'Instrument Serif', 'Noto Serif KR', serif;
--font-mono:  'Geist Mono', 'IBM Plex Sans KR', ui-monospace, monospace;
```

CSS font fallback resolves per glyph: Latin keeps Geist and Instrument Serif exactly as designed, and
only Hangul falls through. Pretendard is a **local name only** — never a CDN `@font-face` — so a
shared file degrades to IBM Plex Sans KR and still renders. For a deliverable, embed a subset instead:
`python3 <skill-dir>/scripts/embed_font.py <file>` (~11 KB per weight).

**Load-bearing rule:** Mono is for *technical* content (ports, commands, URLs, field types). Names go
in the sans stack. Page title is the serif stack. Italic Instrument Serif is reserved for annotation
callouts (see [primitive-annotation.md](primitive-annotation.md)). **Never JetBrains Mono** as a
blanket "dev" font. Full rules: [ko-typography.md](ko-typography.md).
"""


def recheck(roles: dict[str, str]) -> tuple[list[str], list[str]]:
    """Run the skin tool's own constraints against the final, overridden roles."""
    sys.path.insert(0, str(SKIN_TOOL.parent))
    import design_md_skin as skin

    wrapped = {role: {"hex": value, "name": "(profile)", "line": ""}
               for role, value in roles.items() if str(value).startswith("#")}
    return skin.check_constraints(wrapped, dark=False)


def run_skin(brand: str, dark: bool) -> dict:
    result = subprocess.run(
        [sys.executable, str(SKIN_TOOL), brand, "--json"] + (["--dark"] if dark else []),
        capture_output=True, text=True,
    )
    if not result.stdout.strip():
        raise RuntimeError(result.stderr.strip()[:400] or f"no output for brand {brand!r}")
    return json.loads(result.stdout)


def strip_header(body: str) -> str:
    return HEADER_RE.sub("", body, count=1)


def render_header(name: str, slug: str, source: str, notes: str, today: str) -> str:
    def clean(value: str) -> str:
        return " ".join(str(value).replace("--", "–").split()) or "none"

    return (
        "<!-- diagram-design-profile\n"
        f"name: {clean(name)}\n"
        f"slug: {slug}\n"
        f"source-url: {clean(source)}\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"notes: {clean(notes)}\n"
        "-->\n"
    )


def substitute_roles(body: str, light: dict[str, str], dark: dict[str, str]) -> tuple[str, list[str]]:
    """Rewrite the light and dark columns of the semantic-roles table in place."""
    applied: list[str] = []
    lines = body.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^\|\s*`([a-z0-9-]+)`\s*\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$", line)
        if not match:
            continue
        role, purpose = match.group(1), match.group(2)
        if role not in ROLES:
            continue
        new_light = light.get(role)
        new_dark = dark.get(role, new_light)
        if not new_light:
            continue
        lines[index] = f"| `{role}` |{purpose}| `{new_light}` | `{new_dark}` |"
        applied.append(role)
    return "\n".join(lines) + ("\n" if body.endswith("\n") else ""), applied


def replace_typography(body: str) -> str:
    start = body.find("## Typography")
    if start == -1:
        return body
    end = body.find("\n---", start)
    if end == -1:
        return body
    return body[:start] + KOREAN_TYPOGRAPHY + body[end:]


def replace_palette_note(body: str, brand: str, source: str) -> str:
    return re.sub(
        r"> \*\*Brand palette source:\*\*[^\n]*\n",
        f"> **Brand palette source:** mapped from the `design-md` token file for **{brand}** "
        f"({source}) via `scripts/design_md_skin.py`, then hand-checked. Roles the brand does not "
        "name directly (`soft`, `rule`, `accent-tint`) are derived from the ones it does.\n",
        body, count=1,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a named client profile from a design-md brand.")
    ap.add_argument("brand", nargs="?", help="design-md brand folder name")
    ap.add_argument("--slug", help="profile slug (default: brand name, dots→hyphens)")
    ap.add_argument("--name", help="display name for the profile header")
    ap.add_argument("--notes", default="none")
    ap.add_argument("--korean", action="store_true", help="use the ko-typography stack and floors")
    ap.add_argument("--set", action="append", default=[], metavar="ROLE=HEX",
                    help="override a proposed role in the light column, repeatable")
    ap.add_argument("--set-dark", action="append", default=[], metavar="ROLE=HEX",
                    help="override a proposed role in the dark column, repeatable")
    ap.add_argument("--seed-default", action="store_true",
                    help="write the pristine shipped guide as the reserved `default` profile")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written")
    args = ap.parse_args()

    today = _dt.date.today().isoformat()
    pristine = STYLE_GUIDE.read_text(encoding="utf-8")
    LIBRARY.mkdir(parents=True, exist_ok=True)

    if args.seed_default:
        target = LIBRARY / "default.md"
        if "#eb6c36" not in pristine:
            print("FAIL working copy is already customized — cannot snapshot it as `default`. "
                  "Restore the shipped style-guide.md first.", file=sys.stderr)
            return 1
        if target.exists():
            print(f"OK {target} already exists — left untouched")
            return 0
        body = render_header("Default", "default", "none", "Pristine shipped style guide", today) + strip_header(pristine)
        if args.dry_run:
            print(body[:400]); return 0
        target.write_text(body, encoding="utf-8")
        print(f"OK wrote {target}")
        return 0

    if not args.brand:
        ap.error("brand is required unless --seed-default is given")

    slug = args.slug or args.brand.replace(".", "-").replace("_", "-").casefold()
    if not SLUG_RE.match(slug):
        print(f"FAIL slug {slug!r} must match [a-z0-9][a-z0-9-]{{0,63}}", file=sys.stderr)
        return 1
    if slug == "default":
        print("FAIL `default` is reserved — use --seed-default", file=sys.stderr)
        return 1

    try:
        light = run_skin(args.brand, dark=False)
        dark = run_skin(args.brand, dark=True)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    light_roles = dict(light["roles"])
    dark_roles = dict(dark["roles"])
    for flag, target_roles in (("--set", light_roles), ("--set-dark", dark_roles)):
        for override in (args.set if flag == "--set" else args.set_dark):
            if "=" not in override:
                print(f"FAIL {flag} expects ROLE=HEX, got {override!r}", file=sys.stderr)
                return 1
            role, _, value = override.partition("=")
            role, value = role.strip(), value.strip()
            if role not in ROLES:
                print(f"FAIL unknown role {role!r}; known roles: {', '.join(ROLES)}", file=sys.stderr)
                return 1
            target_roles[role] = value

    # Re-measure after the overrides. Reporting the raw mapping's warnings would
    # be stale the moment a --set fixes the thing being warned about.
    errors, warnings = recheck(light_roles)

    body = strip_header(pristine)
    body, applied = substitute_roles(body, light_roles, dark_roles)
    body = replace_palette_note(body, args.brand, light["source"])
    if args.korean:
        body = replace_typography(body)

    missing = [r for r in ROLES if r not in applied]
    header = render_header(
        args.name or args.brand, slug, light["source"],
        args.notes if args.notes != "none" else f"design-md {args.brand}" + (" · Korean" if args.korean else ""),
        today,
    )
    output = header + body

    target = LIBRARY / f"{slug}.md"
    if args.dry_run:
        print(f"--- would write {target} ({len(output.encode())} bytes)")
        print(f"    roles applied: {', '.join(applied) or 'none'}")
        if missing:
            print(f"    roles left at shipped default: {', '.join(missing)}")
        for message in errors:
            print(f"    FAIL {message}")
        for message in warnings:
            print(f"    WARN {message}")
        return 0

    target.write_text(output, encoding="utf-8")
    print(f"OK wrote {target}")
    print(f"     roles applied: {', '.join(applied)}")
    if missing:
        print(f"     left at shipped default: {', '.join(missing)} — the brand names no candidate")
    for message in errors:
        print(f"     FAIL {message}", file=sys.stderr)
    for message in warnings:
        print(f"     WARN {message}", file=sys.stderr)
    print(f"     load it with the skill's `load {slug}` verb (references/profiles.md)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
