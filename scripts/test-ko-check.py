#!/usr/bin/env python3
"""Adversarial tests for skills/diagram-design/scripts/ko_check.py.

Both polarities, per ADR 0005: every defect must be reported, and every legal
Korean construction must not be. A checker that only fires is as useless as one
that never does.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills" / "diagram-design" / "scripts"))

import ko_check  # noqa: E402

KO_LINK = (
    '<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600'
    "&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap\" rel=\"stylesheet\">"
)
KO_STACK = "'Geist', 'Pretendard Variable', 'IBM Plex Sans KR', sans-serif"


def document(body: str, *, lang: str = "ko", link: str = KO_LINK, style: str = "") -> str:
    return (
        f'<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8">{link}'
        f"<style>body{{margin:0}} {style}</style></head><body>{body}</body></html>"
    )


def svg(inner: str) -> str:
    return f'<svg viewBox="0 0 600 300" xmlns="http://www.w3.org/2000/svg">{inner}</svg>'


def run(html: str) -> tuple[list[str], list[str], list[str]]:
    path = Path("/tmp/ko_check_fixture.html")
    path.write_text(html, encoding="utf-8")
    return ko_check.verify(path)


CASES: list[tuple[str, str, str]] = []


def case(name: str, html: str, expect: str) -> None:
    CASES.append((name, html, expect))


# --- must be reported -------------------------------------------------------

case(
    "hangul below the 12px floor",
    document(svg(
        f'<rect x="40" y="40" width="200" height="48" />'
        f'<text x="140" y="68" font-size="9" text-anchor="middle" font-family="{KO_STACK}">데이터 적재</text>'
    )),
    "below the 12px floor",
)

case(
    "font stack with no Hangul coverage",
    document(svg(
        '<rect x="40" y="40" width="240" height="48" />'
        '<text x="160" y="68" font-size="12" text-anchor="middle" '
        "font-family=\"'Geist', 'Geist Mono'\">인증 서버</text>"
    )),
    "no family that ships Hangul",
)

case(
    "hangul label overruns its node box",
    document(svg(
        '<rect x="40" y="40" width="120" height="48" />'
        f'<text x="100" y="68" font-size="12" text-anchor="middle" font-family="{KO_STACK}">'
        "실시간 데이터 파이프라인</text>"
    )),
    "widen the node",
)

case(
    "hangul arrow label overruns its mask",
    document(svg(
        '<rect x="282" y="120" width="36" height="12" />'
        f'<text x="300" y="129" font-size="12" text-anchor="middle" font-family="{KO_STACK}">'
        "일 배치 적재</text>"
    )),
    "size the mask",
)

case(
    "no Korean family in the font link",
    document(
        svg(
            '<rect x="40" y="40" width="240" height="48" />'
            f'<text x="160" y="68" font-size="12" text-anchor="middle" font-family="{KO_STACK}">'
            "인증 서버</text>"
        ),
        link='<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600&display=swap" rel="stylesheet">',
    ),
    "no Korean family in the Google Fonts link",
)

case(
    "svg text with no declared family",
    document(svg(
        '<rect x="40" y="40" width="240" height="48" />'
        '<text x="160" y="68" font-size="12" text-anchor="middle">인증 서버</text>'
    )),
    "declares no font-family",
)

case(
    "wide tracking on hangul",
    document(svg(
        f'<text x="40" y="30" font-size="12" letter-spacing="0.18em" font-family="{KO_STACK}">'
        "데이터 플랫폼</text>"
    )),
    "read as broken spacing",
)

case(
    "korean prose without keep-all",
    document(
        '<p class="note">이 다이어그램은 데이터 플랫폼의 적재 경로를 보여준다</p>',
        style=".note{line-height:1.7}",
    ),
    "keep-all",
)

case(
    "uppercase on a hangul eyebrow",
    document(
        '<p class="eyebrow">아키텍처 diagram</p>',
        style=".eyebrow{text-transform:uppercase;letter-spacing:0.18em}",
    ),
    "text-transform: uppercase",
)

case(
    "lang not set to ko",
    document(
        svg(
            '<rect x="40" y="40" width="240" height="48" />'
            f'<text x="160" y="68" font-size="12" text-anchor="middle" font-family="{KO_STACK}">'
            "인증 서버</text>"
        ),
        lang="en",
    ),
    'set lang="ko"',
)

case(
    "label written as report prose",
    document(svg(
        '<rect x="40" y="40" width="320" height="48" />'
        f'<text x="200" y="68" font-size="12" text-anchor="middle" font-family="{KO_STACK}">'
        "적재에 대한 검증</text>"
    )),
    "reads as report prose",
)

# --- must NOT be reported ---------------------------------------------------

CLEAN: list[tuple[str, str]] = []


def clean(name: str, html: str) -> None:
    CLEAN.append((name, html))


clean(
    "a correctly sized korean node",
    document(svg(
        '<rect x="40" y="40" width="160" height="48" />'
        f'<text x="120" y="68" font-size="12" text-anchor="middle" font-family="{KO_STACK}">인증 서버</text>'
    )),
)

clean(
    "latin sublabel at 9px alongside hangul",
    document(svg(
        '<rect x="40" y="40" width="160" height="56" />'
        f'<text x="120" y="64" font-size="12" text-anchor="middle" font-family="{KO_STACK}">인증 서버</text>'
        "<text x=\"120\" y=\"80\" font-size=\"9\" text-anchor=\"middle\" font-family=\"'Geist Mono', monospace\">:8443/oauth</text>"
    )),
)

clean(
    "free-floating title outside any rect",
    document(svg(
        '<rect x="0" y="0" width="600" height="300" fill="#f5f5f5"/>'
        f'<text x="30" y="200" font-size="12" font-family="{KO_STACK}">범례 · 데이터 흐름 경로 표시</text>'
    )),
)

clean(
    "hangul under a transformed group is skipped, not guessed",
    document(svg(
        '<g transform="rotate(-90 100 100)">'
        '<rect x="40" y="40" width="60" height="20" />'
        f'<text x="70" y="54" font-size="12" text-anchor="middle" font-family="{KO_STACK}">'
        "처리량 지표</text></g>"
    )),
)

clean(
    "korean prose with keep-all and generous leading",
    document(
        '<p class="note">이 다이어그램은 데이터 플랫폼의 적재 경로를 보여준다</p>',
        style=".note{word-break:keep-all;overflow-wrap:break-word;line-height:1.7}",
    ),
)

clean(
    "an english-only diagram is untouched by the korean layer",
    document(
        svg(
            '<rect x="40" y="40" width="120" height="48" />'
            "<text x=\"100\" y=\"68\" font-size=\"8\" text-anchor=\"middle\" font-family=\"'Geist Mono', monospace\">DAILY BATCH</text>"
        ),
        lang="en",
        link='<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600&display=swap" rel="stylesheet">',
    ),
)


def main() -> int:
    failures = 0

    for name, html, expect in CASES:
        errors, warnings, notes = run(html)
        haystack = " | ".join(errors + warnings + notes)
        if expect not in haystack:
            print(f"FAIL [reports] {name}: expected {expect!r}\n      got: {haystack or '(nothing)'}")
            failures += 1

    for name, html in CLEAN:
        errors, warnings, notes = run(html)
        noise = [m for m in errors + warnings if "no Hangul" not in m]
        if noise:
            print(f"FAIL [clean] {name}: unexpected report(s):")
            for message in noise:
                print(f"      {message}")
            failures += 1

    total = len(CASES) + len(CLEAN)
    if failures:
        print(f"\n{failures}/{total} ko_check cases failed")
        return 1
    print(f"OK ko_check: {len(CASES)} defects reported, {len(CLEAN)} legal cases stayed quiet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
