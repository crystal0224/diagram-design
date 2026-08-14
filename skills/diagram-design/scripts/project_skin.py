#!/usr/bin/env python3
"""Read a project's own design tokens and map them onto Diagram Design's roles.

    python3 <skill-dir>/scripts/project_skin.py ~/code/my-app
    python3 <skill-dir>/scripts/project_skin.py ./web --dark --json
    python3 <skill-dir>/scripts/project_skin.py . --max-files 40

A diagram embedded in a designed page must not arrive wearing a different
palette. `design_md_skin.py` answers "skin this like <brand>"; this answers the
more common case — "skin this like *this codebase*", where the design decisions
already exist in CSS custom properties, a Tailwind theme, or a token file.

It reuses the same role mapping and the same constraint gate as the brand
bridge, so the measurements mean the same thing: WCAG AA on ink and muted,
exactly one accent, paper that is not pure white. Only the source differs.

Scans, in order of trust: CSS/SCSS custom properties (`--color-ink: #1c1917`),
Tailwind theme colors, and JSON/TS token files. A declaration's *name* is what
assigns its role, so `--surface-muted` lands where a bare hex could not.

Output is proposed, not decided — see references/frontend-design-bridge.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design_md_skin as skin  # noqa: E402 — shares the mapping and the gate

TOKEN_GLOBS = [
    "**/*.css", "**/*.scss", "**/*.sass",
    "**/tailwind.config.*", "**/theme.*", "**/tokens.*",
    "**/design-tokens.*", "**/*.tokens.json",
]
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "out", "vendor",
             "__pycache__", ".venv", "venv", "coverage", ".cache"}
# A declaration name is the strongest role signal a codebase gives us.
DECL_RE = re.compile(
    r"""(?P<name>--[a-zA-Z0-9_-]+|['"]?[a-zA-Z][a-zA-Z0-9_.-]*['"]?)\s*[:=]\s*['"]?"""
    r"""(?P<hex>\#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}))\b"""
)
MIN_DISTINCT_COLORS = 4


def is_skipped(path: Path, root: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1])


def collect_files(root: Path, max_files: int) -> list[Path]:
    seen: list[Path] = []
    for pattern in TOKEN_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file() or is_skipped(path, root) or path in seen:
                continue
            seen.append(path)
            if len(seen) >= max_files:
                return seen
    return seen


def declarations(files: list[Path], root: Path) -> list[dict]:
    """Every named hex declaration, shaped like design_md_skin's candidates."""
    found: list[dict] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # A dark-theme block should not be mistaken for the light palette.
        for match in DECL_RE.finditer(text):
            name = match.group("name").strip("'\"").lstrip("-")
            hex_value = skin.normalize(match.group("hex"))
            line_start = text.rfind("\n", 0, match.start()) + 1
            line = text[line_start:text.find("\n", match.start())].strip()
            found.append({
                "hex": hex_value,
                "name": name.replace("-", " ").replace("_", " ").casefold(),
                "line": f"{path.relative_to(root)}: {line[:120]}",
                "luminance": skin.relative_luminance(hex_value),
                "saturation": skin.saturation(hex_value),
            })
    return found


def split_by_theme(found: list[dict], dark: bool) -> list[dict]:
    """Prefer declarations whose context names the requested theme, if any do."""
    marker = "dark" if dark else "light"
    themed = [i for i in found if marker in i["line"].casefold() or marker in i["name"]]
    if dark:
        return themed or found
    # For light, actively drop anything that announces itself as dark.
    return [i for i in found if "dark" not in i["line"].casefold() and "dark" not in i["name"]] or found


def main() -> int:
    ap = argparse.ArgumentParser(description="Map a project's design tokens onto Diagram Design roles.")
    ap.add_argument("root", type=Path, help="project directory to scan")
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-files", type=int, default=60)
    args = ap.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"FAIL {root} is not a directory", file=sys.stderr)
        return 1

    files = collect_files(root, args.max_files)
    if not files:
        print(f"FAIL no CSS / Tailwind / token files under {root}. "
              "If the project styles inline or through a component library, use "
              "design_md_skin.py with the nearest brand instead.", file=sys.stderr)
        return 1

    found = split_by_theme(declarations(files, root), args.dark)
    distinct = {i["hex"] for i in found}
    if len(distinct) < MIN_DISTINCT_COLORS:
        print(f"FAIL found {len(distinct)} distinct color(s) across {len(files)} file(s) — "
              "not enough to derive a skin. The project may theme through a library "
              "rather than its own tokens.", file=sys.stderr)
        return 1

    roles, ranked, notes = skin.assign_roles(found, args.dark)
    errors, warnings = skin.check_constraints(roles, args.dark)
    structure = {"fonts": [], "radii": []}

    if args.json:
        print(json.dumps({
            "root": str(root), "files_scanned": len(files), "distinct_colors": len(distinct),
            "dark": args.dark,
            "roles": {k: v["hex"] for k, v in roles.items()},
            "alternates": {k: [o["hex"] for o in v[1:4]] for k, v in ranked.items() if len(v) > 1},
            "errors": errors, "warnings": warnings, "notes": notes,
        }, ensure_ascii=False, indent=2))
    else:
        print(skin.render_report(root.name, f"{len(files)} token file(s) under {root}",
                                 roles, ranked, structure, notes, errors, warnings, args.dark))
        print()
        print("Sources read:")
        for path in files[:8]:
            print(f"  {path.relative_to(root)}")
        if len(files) > 8:
            print(f"  … and {len(files) - 8} more")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
