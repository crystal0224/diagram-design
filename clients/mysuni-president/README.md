# mySUNI President profile

This client overlay binds Diagram Design to the governed
`artifact-template-mysuni-lecture-2026` native-diagram register.

Install the profile body as:

```text
~/.diagram-design/profiles/mysuni-president.md
```

Then place this exact marker in the project root:

```text
profile: mysuni-president
```

The profile is for deterministic HTML/SVG studies and browser QA. PowerPoint
delivery remains native and editable; do not flatten a study screenshot into a
finished lecture slide.

## Acceptance sample

`samples/philosophy-lab.html` exercises three different relationship grammars:

1. a hierarchy and branch (Plato's divided line),
2. a model / condition / ordering relation (`Timaeus`), and
3. a governed material flow from frozen source to lecture deck.

Run the shared checks and the client contract together:

```bash
python3 skills/diagram-design/scripts/self_check.py clients/mysuni-president/samples/philosophy-lab.html
python3 scripts/verify-geometry.py clients/mysuni-president/samples/philosophy-lab.html
python3 skills/diagram-design/scripts/render_check.py clients/mysuni-president/samples/philosophy-lab.html --shot /tmp/mysuni-diagram-shots
python3 clients/mysuni-president/scripts/check_lab.py clients/mysuni-president/samples/philosophy-lab.html
python3 clients/mysuni-president/scripts/export_semantic_topology.py clients/mysuni-president/samples/philosophy-lab.html
```

`ko_check.py` scopes boxes per SVG, so a gallery with repeated coordinates is
checked without cross-diagram false positives. The semantic exporter writes a
sidecar JSON containing node roles, geometry, typed relations, and SVG paths.
That sidecar is the handoff contract for rebuilding a selected study with native
PowerPoint objects; the browser screenshot remains preview-only.
