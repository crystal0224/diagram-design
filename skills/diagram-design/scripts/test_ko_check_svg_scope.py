#!/usr/bin/env python3
"""Regression tests for per-SVG geometry scoping in ko_check.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import ko_check


DOCUMENT = """<!doctype html>
<html lang="ko"><head>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR">
<style>body{word-break:keep-all} svg text{font-family:'IBM Plex Sans KR',sans-serif;font-size:23px}</style>
</head><body>
<svg viewBox="0 0 320 80">
  <rect x="0" y="0" width="300" height="60"/>
  <text x="10" y="35">충분히 긴 한글</text>
</svg>
<svg viewBox="0 0 80 80">
  <rect x="0" y="0" width="50" height="60"/>
</svg>
</body></html>"""


class SvgScopeTest(unittest.TestCase):
    def verify_text(self, source: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.html"
            path.write_text(source, encoding="utf-8")
            errors, _, _ = ko_check.verify(path)
        return errors

    def test_rect_in_other_svg_does_not_capture_label(self) -> None:
        self.assertEqual(self.verify_text(DOCUMENT), [])

    def test_real_overflow_in_same_svg_still_fails(self) -> None:
        source = DOCUMENT.replace('width="300"', 'width="80"', 1)
        errors = self.verify_text(source)
        self.assertTrue(any("needs ~" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
