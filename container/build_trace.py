#!/usr/bin/env python3
"""Package step: emit the interactive traceability graph as a run output.

Builds /output/traceability.html from the run's own artifacts:
  - the ARS Reporting Event with results written back (from package.R)
  - the bundled USDM objective/endpoint fixture (the ARS carries no USDM ids)
  - coverage.json / manifest.json  -> per-output run status (mode, rendered, repairs)
  - ard.csv                        -> ARD result-row counts per output

The graph model is built by the shared builder in /app/viz/build_graph.py and
injected into /app/viz/traceability.template.html. Output is pure ASCII so it
renders regardless of how it is served. This step is best-effort: a failure here
must not fail the run (the coverage gate in package.R is the conformance test),
so main() never raises.

Usage:
  python3 build_trace.py --ars /output/reporting_event_with_results.json \
      --usdm /app/fixtures/usdm_trace.json --coverage /workspace/coverage.json \
      --manifest /output/manifest.json --ard /output/ard.csv \
      --template /app/viz/traceability.template.html --out /output/traceability.html
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app/viz")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))  # local dev fallback


def _load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _run_annotations(coverage, manifest, ard_path):
    """Per-output {mode, rendered, ardRows, repairs} from the run's own artifacts."""
    run = {}
    for c in (coverage or {}).get("outputs", []) or []:
        oid = c.get("outputId")
        if not oid:
            continue
        run[oid] = {"mode": c.get("mode"), "rendered": c.get("status") == "rendered",
                    "repairs": c.get("repairs")}
    for p in (manifest or {}).get("perOutput", []) or []:
        oid = p.get("outputId")
        if not oid:
            continue
        run.setdefault(oid, {})
        run[oid]["mode"] = run[oid].get("mode") or p.get("mode")
        if "rendered" in p:
            run[oid]["rendered"] = p.get("rendered")
    # ARD rows per output
    try:
        with open(ard_path, newline="", encoding="utf-8") as fh:
            counts = Counter(row.get("output_id", "") for row in csv.DictReader(fh))
        for oid, n in counts.items():
            if oid:
                run.setdefault(oid, {})["ardRows"] = n
    except (OSError, ValueError):
        pass
    return run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ars", default="/output/reporting_event_with_results.json")
    ap.add_argument("--ars-fallback", default="/workspace/reporting_event.json")
    ap.add_argument("--usdm", default="/app/fixtures/usdm_trace.json")
    ap.add_argument("--coverage", default="/workspace/coverage.json")
    ap.add_argument("--manifest", default="/output/manifest.json")
    ap.add_argument("--ard", default="/output/ard.csv")
    ap.add_argument("--template", default="/app/viz/traceability.template.html")
    ap.add_argument("--out", default="/output/traceability.html")
    a = ap.parse_args()

    try:
        import build_graph  # from /app/viz (or local viz/)
    except ImportError as e:
        print(f"[build_trace] cannot import build_graph ({e}); skipping interactive HTML", file=sys.stderr)
        return 0

    ars = _load(a.ars) or _load(a.ars_fallback)
    if not ars:
        print("[build_trace] no Reporting Event found; skipping interactive HTML", file=sys.stderr)
        return 0

    usdm = _load(a.usdm) or {}
    objectives = usdm.get("objectives", [])
    ep2out = usdm.get("endpointOutputMap", {})
    pop_context = usdm.get("populationContext", {})

    run = _run_annotations(_load(a.coverage), _load(a.manifest), a.ard)

    try:
        graph = build_graph.graph(ars, objectives, ep2out, pop_context, run)
        tpl = Path(a.template).read_text(encoding="utf-8")
        if "__DATA__" not in tpl:
            raise ValueError("template missing __DATA__ placeholder")
        out = tpl.replace("__DATA__", json.dumps(graph, separators=(",", ":"), ensure_ascii=True))
        Path(a.out).write_text(out, encoding="utf-8")
    except (OSError, ValueError, KeyError) as e:
        print(f"[build_trace] failed to build interactive HTML ({e}); skipping", file=sys.stderr)
        return 0

    traced = sum(1 for n in graph["nodes"] if n["kind"] == "endpoint")
    linked = len({e["from"] for e in graph["edges"] if e["rel"] == "evaluated by"})
    print(f"[build_trace] wrote {a.out} | {len(graph['nodes'])} nodes, "
          f"{len(graph['edges'])} edges | {linked}/{traced} endpoints traced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
