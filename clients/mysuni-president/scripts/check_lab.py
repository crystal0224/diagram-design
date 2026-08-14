#!/usr/bin/env python3
"""Client-specific acceptance checks for the mySUNI philosophy gallery."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REQUIRED = {
    "canvas": 'viewBox="0 0 1152 500"',
    "background": "#071524",
    "accent": "#69D5F5",
    "primary text": "#F7F9FC",
    "conclusion": "#D7A45A",
    "sans family": "Pretendard",
    "serif family": "NanumMyeongjo",
}

FORBIDDEN_COLORS = ("#FF0000", "#00FF00", "#FF3B30", "#34C759")


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "clients/mysuni-president/samples/philosophy-lab.html")
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []

    if text.count("<svg") != 3:
        failures.append("gallery must contain exactly three SVG studies")
    if len(re.findall(r'data-node-id="[^"]+"', text)) != 17:
        failures.append("gallery must expose all 17 semantic nodes for native rebuild")
    if len(re.findall(r'data-edge-id="[^"]+"', text)) != 14:
        failures.append("gallery must expose all 14 semantic edges for native rebuild")
    if len(re.findall(r'data-source="[^"]+"\s+data-target="[^"]+"', text)) != 14:
        failures.append("every semantic edge must declare source and target")
    if text.count(REQUIRED["canvas"]) != 3:
        failures.append("every study must use the 1152 x 500 relationship canvas")
    if len(re.findall(r'<svg[^>]+role="img"', text)) != 3:
        failures.append("every SVG must expose role=img")
    if len(re.findall(r'<svg[^>]+aria-labelledby="[^"]+"', text)) != 3:
        failures.append("every SVG must resolve an aria-labelledby pair")
    if text.count("<title") != 4 or text.count("<desc") != 3:
        failures.append("document title plus three SVG title/description pairs are required")

    for label, token in REQUIRED.items():
        if token.lower() not in text.lower():
            failures.append(f"missing {label} token: {token}")
    for token in FORBIDDEN_COLORS:
        if token.lower() in text.lower():
            failures.append(f"forbidden red/green token: {token}")

    if "font-size:23px" not in text.replace(" ", ""):
        failures.append("meaning-bearing SVG labels must retain the 23 px floor")
    if "class=\"conclusion\"" not in text or "font-size:38px" not in text.replace(" ", ""):
        failures.append("the NanumMyeongjo conclusion register is missing")
    if "<script" in text.lower():
        failures.append("the review gallery must stay script-free and deterministic")

    if failures:
        print(f"FAIL {path}")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"OK {path}: mySUNI profile contract satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
