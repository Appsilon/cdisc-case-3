#!/usr/bin/env python3
"""Build the self-contained traceability visualization.

Injects the derived trace graph (trace_graph.json) into the HTML template
(traceability.template.html) to produce traceability.html.

The output is deliberately pure-ASCII (JSON is emitted with ensure_ascii=True and
the template's own glyphs are HTML entities / \\u escapes) so the page renders
correctly regardless of how it is served or wrapped.

    python build.py

trace_graph.json is regenerated from the ARS Reporting Event + USDM by
build_graph.py (see README.md); it is committed so this step needs no external
study data.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACEHOLDER = "__DATA__"


def main() -> None:
    tpl = (HERE / "traceability.template.html").read_text(encoding="utf-8")
    data = json.loads((HERE / "trace_graph.json").read_text(encoding="utf-8"))
    if PLACEHOLDER not in tpl:
        raise SystemExit("template is missing the __DATA__ placeholder")
    compact = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
    out = tpl.replace(PLACEHOLDER, compact)
    if any(ord(c) > 127 for c in out):
        raise SystemExit("output is not pure ASCII")
    (HERE / "traceability.html").write_text(out, encoding="utf-8")
    print(f"wrote traceability.html ({len(out.encode('utf-8'))} bytes, "
          f"{len(data['nodes'])} nodes, {len(data['edges'])} edges)")


if __name__ == "__main__":
    main()
