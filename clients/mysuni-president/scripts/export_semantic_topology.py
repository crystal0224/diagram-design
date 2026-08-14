#!/usr/bin/env python3
"""Export mySUNI SVG diagrams as editable node/edge topology JSON.

The HTML remains the visual review artifact. Explicit ``data-node-*`` and
``data-edge-*`` attributes carry the semantic layer needed to rebuild a chosen
diagram as native PowerPoint shapes without reverse-engineering its pixels.
"""

from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


def number(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


class SemanticParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section_id: str | None = None
        self.diagram: dict[str, Any] | None = None
        self.diagrams: list[dict[str, Any]] = []
        self.capture: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag == "section":
            self.section_id = data.get("id") or None
        elif tag == "svg":
            self.diagram = {
                "id": self.section_id or f"diagram-{len(self.diagrams) + 1}",
                "viewBox": data.get("viewBox", ""),
                "title": "",
                "description": "",
                "nodes": [],
                "edges": [],
            }
        elif self.diagram is not None and tag in {"title", "desc"}:
            self.capture = tag
        elif self.diagram is not None and tag == "rect" and data.get("data-node-id"):
            self.diagram["nodes"].append(
                {
                    "id": data["data-node-id"],
                    "label": data.get("data-label", ""),
                    "role": data.get("data-role", "concept"),
                    "shape": "rounded-rect" if number(data.get("rx")) else "rect",
                    "geometry": {
                        "x": number(data.get("x")) or 0,
                        "y": number(data.get("y")) or 0,
                        "width": number(data.get("width")),
                        "height": number(data.get("height")),
                        "radius": number(data.get("rx")) or 0,
                    },
                    "styleClass": data.get("class", ""),
                }
            )
        elif self.diagram is not None and tag == "path" and data.get("data-edge-id"):
            self.diagram["edges"].append(
                {
                    "id": data["data-edge-id"],
                    "source": data.get("data-source", ""),
                    "target": data.get("data-target", ""),
                    "relation": data.get("data-relation", ""),
                    "path": data.get("d", ""),
                    "styleClass": data.get("class", ""),
                }
            )

    def handle_data(self, data: str) -> None:
        if self.diagram is None or self.capture is None:
            return
        key = "title" if self.capture == "title" else "description"
        self.diagram[key] += data.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"title", "desc"}:
            self.capture = None
        elif tag == "svg" and self.diagram is not None:
            self.diagrams.append(self.diagram)
            self.diagram = None
        elif tag == "section":
            self.section_id = None


def validate(diagrams: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    seen_diagrams: set[str] = set()
    for diagram in diagrams:
        diagram_id = diagram["id"]
        if diagram_id in seen_diagrams:
            failures.append(f"duplicate diagram id: {diagram_id}")
        seen_diagrams.add(diagram_id)

        node_ids = [node["id"] for node in diagram["nodes"]]
        if len(node_ids) != len(set(node_ids)):
            failures.append(f"{diagram_id}: duplicate node id")
        edge_ids = [edge["id"] for edge in diagram["edges"]]
        if len(edge_ids) != len(set(edge_ids)):
            failures.append(f"{diagram_id}: duplicate edge id")
        known = set(node_ids)
        for edge in diagram["edges"]:
            if edge["source"] not in known or edge["target"] not in known:
                failures.append(
                    f"{diagram_id}: edge {edge['id']} references unknown nodes "
                    f"{edge['source']} -> {edge['target']}"
                )
        if not node_ids:
            failures.append(f"{diagram_id}: no semantic nodes")
        if not edge_ids:
            failures.append(f"{diagram_id}: no semantic edges")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Export editable mySUNI diagram topology JSON")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    output = (args.output or source.with_suffix(".semantic.json")).resolve()
    semantic = SemanticParser()
    semantic.feed(source.read_text(encoding="utf-8"))
    semantic.close()

    failures = validate(semantic.diagrams)
    if failures:
        for failure in failures:
            print(f"FAIL {source}: {failure}", file=sys.stderr)
        return 1

    payload = {
        "schema": "mysuni.diagram-topology/v1",
        "source": source.name,
        "coordinateSpace": "SVG viewBox",
        "authority": "visual-structure-only",
        "diagrams": semantic.diagrams,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"OK {output}: {len(semantic.diagrams)} diagrams, "
        f"{sum(len(item['nodes']) for item in semantic.diagrams)} nodes, "
        f"{sum(len(item['edges']) for item in semantic.diagrams)} edges"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
