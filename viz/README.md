# viz — interactive objective→result traceability

A self-contained, interactive graph that traces every planned result back to the
study objective it answers and down to the ADaM data it reads. It is the
human-facing view of the traceability this workflow produces by construction — the
`assemble-trace` step is intended to emit this page as a run artifact.

Open **`traceability.html`** in any browser (no server, no network).

## What it shows

Six CDISC layers, left→right from intent to provenance:

```
Objective (USDM) → Endpoint (USDM) → Output/TFL (ARS) → Analysis (ARS) → Method (ARS) → ADaM dataset
```

- **Click any node** to trace its full lineage (upstream to the objective,
  downstream to the data); the detail drawer shows the CDISC metadata and a
  clickable layer-by-layer chain.
- **Standard vs custom** outputs are distinguished (solid = validated recipe;
  dashed + "AI" = AI-drafted, human-reviewed efficacy program).
- **Traceability gaps** — endpoints with no defined result — are flagged in red.
  For the bundled CDISCPILOT01 Common Safety Displays subset, 3 of 11 endpoints
  are traced; the rest (CIBIC+, labs, secondary/TBD endpoints) have no output in
  this ARS and show as gaps.

## Files

| File | Role |
|------|------|
| `traceability.html` | the built, self-contained page (pure ASCII) |
| `traceability.template.html` | HTML/CSS/JS template with a `__DATA__` placeholder |
| `trace_graph.json` | the derived node/edge model (committed, so the build needs no external data) |
| `build.py` | inject `trace_graph.json` into the template → `traceability.html` |
| `build_graph.py` | regenerate `trace_graph.json` from the ARS Reporting Event + study USDM |

## Rebuild

```bash
# after editing the template or the data model:
python build.py

# to regenerate the data model from source (needs the study USDM):
python build_graph.py --usdm /path/to/CDISC_Pilot_Study.json
python build.py
```

The ARS half of the graph (Output→Analysis→Method→dataset) is extracted verbatim
from `../fixtures/reporting_event.json`. The USDM half (Objective→Endpoint) comes
from the study USDM; Endpoint→Output is a curated semantic mapping documented in
`build_graph.py`.
