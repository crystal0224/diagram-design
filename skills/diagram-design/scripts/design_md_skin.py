#!/usr/bin/env python3
"""Map a design-md brand DESIGN.md onto Diagram Design's semantic roles.

    python3 <skill-dir>/scripts/design_md_skin.py montage
    python3 <skill-dir>/scripts/design_md_skin.py linear.app --dark
    python3 <skill-dir>/scripts/design_md_skin.py notion --structure-only
    python3 <skill-dir>/scripts/design_md_skin.py vercel --file ./DESIGN.md --json

The design-md skill ships ~62 brand token files. Diagram Design consumes color by
*semantic role* (paper / ink / muted / soft / rule / accent / link), never by hex,
so a brand skin is a role mapping — not a palette dump. This tool does the
mechanical half: pull the candidate hexes out of the brand's tables, assign them
to roles by luminance and token naming, and then check the result against the
constraints in references/style-guide.md that a brand palette most often breaks:

  * `ink` on `paper` must reach WCAG AA (4.5:1); `muted` on `paper` likewise
  * exactly one `accent` — a brand shipping eight colors still gets one focal
  * `paper` is a warm or cool neutral, not pure `#ffffff`

It prints findings rather than silently repairing them: which role each hex came
from, what passed, and what a human has to decide. Judgment stays with the agent
(references/design-md-bridge.md); measurement lives here.

Exit code 1 when a hard constraint fails.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

LOCAL_ROOTS = [
    Path.home() / ".claude" / "awesome-design-md" / "design-md",
    Path.home() / ".codex" / "awesome-design-md" / "design-md",
]
RAW_URL = "https://raw.githubusercontent.com/VoltAgent/awesome-design-md/main/design-md/{brand}/DESIGN.md"

HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
FONT_RE = re.compile(r"(?:font-family|Font|Typeface|서체)\s*[:|]\s*([^|\n]+)", re.I)
RADIUS_RE = re.compile(r"radius[^|\n]*?(\d+(?:\.\d+)?)\s*(?:px|pt)", re.I)

# Token-name keywords → Diagram Design semantic role. Order matters: the first
# matching group wins, so the more specific keywords come first.
ROLE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("accent", ("primary", "brand", "accent", "action", "cta", "interactive")),
    ("link", ("link", "info", "hyperlink")),
    ("rule", ("border", "divider", "outline", "separator", "stroke", "line")),
    ("paper", ("background", "surface", "canvas", "paper", "bg", "base", "elevated", "fill")),
    ("ink", ("label", "text", "foreground", "ink", "content", "onsurface", "on-surface")),
    ("muted", ("secondary", "muted", "subtle", "neutral", "alternative", "tertiary", "assistive")),
]

# Roles Diagram Design derives rather than reads from a brand.
DERIVED_NOTE = {
    "paper-2": "paper darkened ~4% (light) / lightened ~4% (dark)",
    "soft": "muted lightened toward paper — sublabels and boundary labels",
    "rule": "ink at 12% opacity when the brand names no border color",
    "rule-solid": "the brand's border color, or muted at 25%",
    "accent-tint": "accent at 8% opacity (light) / 10% (dark)",
}


# --- color math -------------------------------------------------------------


def to_rgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def relative_luminance(hex_value: str) -> float:
    def channel(component: int) -> float:
        srgb = component / 255
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = to_rgb(hex_value)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def saturation(hex_value: str) -> float:
    r, g, b = (c / 255 for c in to_rgb(hex_value))
    high, low = max(r, g, b), min(r, g, b)
    return 0.0 if high == 0 else (high - low) / high


def normalize(hex_value: str) -> str:
    value = hex_value.lstrip("#").lower()
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return f"#{value}"


def with_alpha(hex_value: str, alpha: float) -> str:
    r, g, b = to_rgb(hex_value)
    return f"rgba({r},{g},{b},{alpha})"


def mix(a: str, b: str, ratio: float) -> str:
    ra, ga, ba = to_rgb(a)
    rb, gb, bb = to_rgb(b)
    blend = lambda x, y: round(x + (y - x) * ratio)  # noqa: E731
    return f"#{blend(ra, rb):02x}{blend(ga, gb):02x}{blend(ba, bb):02x}"


# --- sourcing ---------------------------------------------------------------


def load_design_md(brand: str, explicit: Path | None) -> tuple[str, str]:
    if explicit is not None:
        return explicit.read_text(encoding="utf-8"), str(explicit)
    for root in LOCAL_ROOTS:
        candidate = root / brand / "DESIGN.md"
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
            # Most upstream brands ship only a README stub pointing at the paid site.
            if len(HEX_RE.findall(text)) >= 4:
                return text, str(candidate)
    url = RAW_URL.format(brand=brand)
    request = urllib.request.Request(url, headers={"User-Agent": "diagram-design/design-md-bridge"})
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 — pinned host
        return response.read().decode("utf-8"), url


# --- extraction -------------------------------------------------------------


def candidates(text: str, dark: bool) -> list[dict]:
    """Every hex in the file, tagged with the row's token name and column."""
    found: list[dict] = []
    for line in text.splitlines():
        hexes = HEX_RE.findall(line)
        if not hexes:
            continue
        cells = [c.strip() for c in line.split("|")] if "|" in line else [line.strip()]
        name = ""
        for cell in cells:
            if cell and not HEX_RE.search(cell):
                name = cell.strip("`* ")
                break
        # In a "| token | light | dark |" table the second hex is the dark value.
        positions = [(m.start(), m.group(0)) for m in HEX_RE.finditer(line)]
        chosen = positions[1][1] if dark and len(positions) > 1 else positions[0][1]
        found.append({
            "hex": normalize(chosen),
            "name": name.lower(),
            "line": line.strip(),
            "luminance": relative_luminance(normalize(chosen)),
            "saturation": saturation(normalize(chosen)),
        })
    return found


def role_of(name: str, context: str) -> str | None:
    haystack = f"{name} {context}".lower()
    for role, keywords in ROLE_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return role
    return None


def is_blueish(item: dict) -> bool:
    r, g, b = to_rgb(item["hex"])
    return b > r + 12 and b > g + 4


def dedupe(pool: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for item in pool:
        if item["hex"] in seen:
            continue
        seen.add(item["hex"])
        unique.append(item)
    return unique


def assign_roles(found: list[dict], dark: bool) -> tuple[dict[str, dict], dict[str, list[dict]], list[str]]:
    """Return (proposal per role, ranked alternates per role, notes).

    A sparse bucket must never shadow a richer one — montage files its real
    secondary text under `labelNeutral`, which keyword-matches `ink`, while the
    `muted` bucket catches one stray near-black. So every role searches the union
    of its own bucket and the buckets it plausibly overlaps, then ranks.
    """
    notes: list[str] = []
    buckets: dict[str, list[dict]] = {}
    for item in found:
        role = role_of(item["name"], item["line"])
        if role:
            buckets.setdefault(role, []).append(item)

    def pool(*names: str, everything: bool = False) -> list[dict]:
        merged = [i for name in names for i in buckets.get(name, [])]
        return dedupe(merged or (found if everything else []))

    ranked: dict[str, list[dict]] = {}

    # paper — lightest low-saturation surface, with pure white explicitly penalized
    # (style-guide.md: "paper is warm-neutral, not pure white").
    def paper_score(item: dict) -> float:
        base = item["luminance"] if not dark else 1 - item["luminance"]
        penalty = 0.12 if item["hex"] in {"#ffffff", "#000000"} else 0.0
        return base - item["saturation"] * 0.5 - penalty

    ranked["paper"] = sorted(pool("paper", everything=True), key=paper_score, reverse=True)[:4]
    paper = ranked["paper"][0] if ranked["paper"] else None

    if paper is None:
        return {}, ranked, ["no usable surface color found in the brand file"]

    # ink — maximum contrast against paper, neutral preferred
    ranked["ink"] = sorted(
        pool("ink", everything=True),
        key=lambda i: (contrast_ratio(i["hex"], paper["hex"]), -i["saturation"]),
        reverse=True,
    )[:4]
    ink = ranked["ink"][0] if ranked["ink"] else None

    # muted — lowest-contrast neutral that still clears AA. Searches muted ∪ ink ∪ rule.
    if ink:
        ink_contrast = contrast_ratio(ink["hex"], paper["hex"])
        def viable_muted(candidates: list[dict]) -> list[dict]:
            return [
                i for i in candidates
                if i["hex"] != ink["hex"]
                and 4.5 <= contrast_ratio(i["hex"], paper["hex"]) < ink_contrast
                and i["saturation"] < 0.45
            ]

        # Keyword buckets first; then the whole set. A codebase names colors by
        # scale (`slate-600`) or by use (`fill`), so the right neutral routinely
        # lands in the wrong bucket — `fill` reads as a surface, not as text.
        # When naming fails, the measurement still holds.
        viable = viable_muted(pool("muted", "ink", "rule")) or viable_muted(dedupe(found))
        ranked["muted"] = sorted(viable, key=lambda i: contrast_ratio(i["hex"], paper["hex"]))[:4]

    # accent — most saturated brand color that actually separates from paper
    accent_pool = [
        i for i in pool("accent") or [i for i in found if i["saturation"] > 0.35]
        if contrast_ratio(i["hex"], paper["hex"]) >= 2.5 and i["saturation"] >= 0.3
    ]
    ranked["accent"] = sorted(accent_pool, key=lambda i: i["saturation"], reverse=True)[:4]

    # link — a blue that is not the accent; greys named "link" are not links
    accent_hex = ranked.get("accent", [{}])[0].get("hex") if ranked.get("accent") else None
    link_pool = [
        i for i in pool("link") + [i for i in found if is_blueish(i)]
        if is_blueish(i) and i["saturation"] >= 0.3 and i["hex"] != accent_hex
        and contrast_ratio(i["hex"], paper["hex"]) >= 3.0
    ]
    ranked["link"] = sorted(dedupe(link_pool), key=lambda i: i["saturation"], reverse=True)[:4]

    # rule-solid — a hairline sits between paper and ink, nearer paper
    rule_pool = [
        i for i in pool("rule")
        if 1.15 <= contrast_ratio(i["hex"], paper["hex"]) <= 4.5
    ]
    ranked["rule-solid"] = sorted(rule_pool, key=lambda i: contrast_ratio(i["hex"], paper["hex"]))[:4]

    roles: dict[str, dict] = {}
    for role in ("paper", "ink", "muted", "accent", "link", "rule-solid"):
        options = ranked.get(role) or []
        if options:
            roles[role] = options[0]
        else:
            notes.append(f"no candidate for `{role}` — the brand file names none; derive it by hand")
    ink = roles.get("ink")
    accent = roles.get("accent")
    muted = roles.get("muted")

    if paper and ink:
        roles["paper-2"] = {"hex": mix(paper["hex"], ink["hex"], 0.06), "name": "(derived)", "line": ""}
    if muted and paper:
        roles["soft"] = {"hex": mix(muted["hex"], paper["hex"], 0.35), "name": "(derived)", "line": ""}
    if ink:
        roles["rule"] = {"hex": with_alpha(ink["hex"], 0.12), "name": "(derived)", "line": ""}
    if accent:
        roles["accent-tint"] = {"hex": with_alpha(accent["hex"], 0.10 if dark else 0.08),
                                "name": "(derived)", "line": ""}
    return roles, ranked, notes


def extract_structure(text: str) -> dict[str, list[str]]:
    fonts: list[str] = []
    for match in FONT_RE.finditer(text):
        value = match.group(1).strip().strip("`*|")
        if value and len(value) < 120:
            fonts.append(value)
    radii = sorted({float(m) for m in RADIUS_RE.findall(text)})
    return {
        "fonts": list(dict.fromkeys(fonts))[:8],
        "radii": [f"{r:g}" for r in radii][:10],
    }


# --- constraints ------------------------------------------------------------


def check_constraints(roles: dict[str, dict], dark: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    paper = roles.get("paper")
    ink = roles.get("ink")
    muted = roles.get("muted")
    accent = roles.get("accent")

    if not paper or not ink:
        errors.append("could not resolve both `paper` and `ink` — the mapping is not usable")
        return errors, warnings

    ratio = contrast_ratio(ink["hex"], paper["hex"])
    if ratio < 4.5:
        errors.append(
            f"ink {ink['hex']} on paper {paper['hex']} is {ratio:.1f}:1 — below WCAG AA (4.5:1). "
            "Darken ink or lighten paper before shipping; the brand's own pairing may assume "
            "larger type than a 12px node label."
        )
    if muted:
        muted_ratio = contrast_ratio(muted["hex"], paper["hex"])
        if muted_ratio < 4.5:
            warnings.append(
                f"muted {muted['hex']} on paper is {muted_ratio:.1f}:1 — Diagram Design puts muted "
                "on 9–12px sublabels, which needs AA. Pick a darker neutral."
            )
    if accent and paper:
        accent_ratio = contrast_ratio(accent["hex"], paper["hex"])
        if accent_ratio < 3.0:
            warnings.append(
                f"accent {accent['hex']} on paper is {accent_ratio:.1f}:1 — a focal node that "
                "doesn't separate from the page has stopped being focal."
            )
    if not dark and paper["hex"] in {"#ffffff", "#fff"}:
        warnings.append(
            "paper is pure white — style-guide.md asks for a neutral with a hint of warmth; "
            "pure white turns the design sterile. Try the brand's second surface token."
        )
    if accent and muted and contrast_ratio(accent["hex"], muted["hex"]) < 1.4:
        warnings.append(
            f"accent {accent['hex']} and muted {muted['hex']} read as the same value — "
            "the one-accent rule needs the accent to be visibly the odd one out."
        )
    return errors, warnings


# --- output -----------------------------------------------------------------


ROLE_ORDER = ["paper", "paper-2", "ink", "muted", "soft", "rule", "rule-solid",
              "accent", "accent-tint", "link"]


def render_report(brand: str, source: str, roles: dict[str, dict], ranked: dict[str, list[dict]],
                  structure: dict, notes: list[str], errors: list[str], warnings: list[str],
                  dark: bool) -> str:
    paper_hex = roles.get("paper", {}).get("hex")
    lines = [f"# {brand} → Diagram Design roles ({'dark' if dark else 'light'})", "",
             f"source: {source}", "",
             "Proposed, not decided — `alternates` are the next-best candidates the brand names.",
             "", "| role | proposed | contrast on paper | from | alternates |", "|---|---|---|---|---|"]
    for role in ROLE_ORDER:
        item = roles.get(role)
        if item is None:
            lines.append(f"| `{role}` | — | — | {DERIVED_NOTE.get(role, 'unresolved')} | — |")
            continue
        origin = item["name"] if item["name"] and item["name"] != "(derived)" else DERIVED_NOTE.get(role, "derived")
        ratio = (f"{contrast_ratio(item['hex'], paper_hex):.1f}:1"
                 if paper_hex and item["hex"].startswith("#") and role != "paper" else "—")
        others = [o["hex"] for o in ranked.get(role, [])[1:4]]
        lines.append(f"| `{role}` | `{item['hex']}` | {ratio} | {origin} | {' '.join(others) or '—'} |")

    lines += ["", "```css", ":root {"]
    for role in ROLE_ORDER:
        item = roles.get(role)
        if item:
            lines.append(f"  --color-{role}: {item['hex']};")
    lines += ["}", "```", ""]

    if structure["fonts"]:
        lines += ["**Typography named by the brand** (Diagram Design allows three families —",
                  "serif for `title`/`callout`, sans for names, mono for technical strings):", ""]
        lines += [f"- {font}" for font in structure["fonts"]]
        lines.append("")
    if structure["radii"]:
        lines += [f"**Radius scale**: {', '.join(structure['radii'])} — Diagram Design uses 4 / 6 / 8; "
                  "pick the three nearest and drop the rest.", ""]

    for message in errors:
        lines.append(f"- FAIL {message}")
    for message in warnings:
        lines.append(f"- WARN {message}")
    for message in notes:
        lines.append(f"- NOTE {message}")
    if not (errors or warnings or notes):
        lines.append("All constraints pass.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Map a design-md brand onto Diagram Design roles.")
    ap.add_argument("brand", help="brand folder name, e.g. montage, linear.app, notion")
    ap.add_argument("--file", type=Path, default=None, help="read a local DESIGN.md instead of resolving the brand")
    ap.add_argument("--dark", action="store_true", help="take the dark column where a table has two")
    ap.add_argument("--structure-only", action="store_true",
                    help="report typography/radius discipline only — keep the project's existing colors")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        text, source = load_design_md(args.brand, args.file)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL cannot load DESIGN.md for {args.brand!r}: {exc}", file=sys.stderr)
        print("      local brands live in ~/.claude/awesome-design-md/design-md/<brand>/;",
              "most upstream brands ship only a README stub and are fetched from GitHub raw.",
              file=sys.stderr)
        return 1

    structure = extract_structure(text)
    if args.structure_only:
        payload = {"brand": args.brand, "source": source, "structure": structure}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"# {args.brand} → structural discipline only (colors untouched)\n")
            print(f"source: {source}\n")
            print("**Typography**")
            for font in structure["fonts"] or ["(none named)"]:
                print(f"- {font}")
            print(f"\n**Radius scale**: {', '.join(structure['radii']) or '(none named)'}")
            print("\nPort the radius scale, the type ramp, and the elevation discipline. "
                  "Leave paper / ink / accent as they are — see references/design-md-bridge.md.")
        return 0

    found = candidates(text, args.dark)
    if len(found) < 4:
        print(f"FAIL {source} contains {len(found)} color(s) — this looks like a README stub, "
              "not a full DESIGN.md", file=sys.stderr)
        return 1

    roles, ranked, notes = assign_roles(found, args.dark)
    errors, warnings = check_constraints(roles, args.dark)

    if args.json:
        print(json.dumps({
            "brand": args.brand, "source": source, "dark": args.dark,
            "roles": {k: v["hex"] for k, v in roles.items()},
            "alternates": {k: [o["hex"] for o in v[1:4]] for k, v in ranked.items() if len(v) > 1},
            "structure": structure,
            "errors": errors, "warnings": warnings, "notes": notes,
        }, ensure_ascii=False, indent=2))
    else:
        print(render_report(args.brand, source, roles, ranked, structure, notes, errors, warnings, args.dark))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
