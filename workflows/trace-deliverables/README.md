# trace-deliverables

One page that connects every deliverable of a protocol-to-TFL run, so any
output can be traced back to the protocol and the SDTM, and any input forward
to the outputs it feeds. Deterministic: no AI, no reviewer. Every link comes
from data the earlier workflows already wrote. Runs inside `protocol-to-tlfs`
after `generate-ard-tlfs`, or on its own with any study package in the trigger.

```
resolve-inputs ─► build-explorer ─► done
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Lists the package files the explorer reads as top-level `files` (the runtime downloads only those). Skips the SDTM datasets, the protocol and SAP PDFs, the CORE spreadsheets / HTML and `tlf-viewer.html`. Fails when there is no package, or no `lineage`, `ard`, `tfl` or `tfl-program`. |
| `build-explorer` | script | sha256-verifies the files, stages them as `<kind>/<name>`, runs `build_explorer.py`, and publishes `traceability-explorer.html` + `traceability.json` (kind `traceability`) into the package. Outcome `traced`. Gaps go in the page, never fail the step. |

## What it links

| Question | Chain | From |
|---|---|---|
| Where does this number come from? | table cell → ARD rows → ARS analysis (set, subset, grouping) → ADaM variables → `@derive` lines → SDTM columns | `data-ard`, `ard/*.json`, `@tlf analysis= uses=`, `reporting-event.json`, `lineage.json` |
| Where does this ADaM variable come from, and what uses it? | declared sources and the SDTM columns named in the code; the `@derive` block plus the earlier statements it reads (intermediate frames traced back to `read_sdtm` / `read_adam`); ADaM variables and outputs that read it; data profile by arm | `lineage.json`, `adam-program/*.R` (`rcode.py`), ADaM `.xpt` (`profile_adam.R`) |
| Why does this output exist? | USDM objective / endpoint → protocol page + quote → TLF plan entry | `usdm.json`, `usdm-citations.json`, `tlf-plan.json` |
| What did CORE say, and what does it touch? | finding → disposition → SDTM columns → ADaM variables built from them → downstream ADaM → outputs | `core-report-<std>/core-report.json`, `core-dispositions-<std>.json` |
| Did the checks pass? | numbers reconciled, big N, statistics recomputed, population counts, per output | `reconciliation.json`, `accuracy.json`, `population-counts.json` |

**Gaps** are links that should exist but don't, and the page lists them. An
output with no `@tlf` tag, an ARD variable that resolves to no ADaM variable,
a `uses=` variable or ADaM column with no lineage entry, a declared source
that is not an ADaM variable, a planned output the run did not produce, and an
objective with no output each count as a gap. Flags on a variable are weaker
signals: a declared SDTM source that the traced code never names, or a source
missing from the SDTM `define.xml`.

## The page

`traceability-explorer.html` is self-contained. The model is JSON in
`<script id="DATA">`, with `explorer.js` and the styles inline. It makes no
external requests, so it renders in the platform's sandboxed iframe. It has
tabs for Outputs, Variables, Protocol, CORE, Checks and Gaps, and every chip
links across tabs (`#out/<id>`, `#var/<DS.VAR>`, `#sdtm/<DOM.COL>`,
`#core/<std|rule|dataset>`, `#protocol/<id>`). On the Outputs tab, clicking a
number in a display traces it.

The displays are HTML written by AI-authored programs, so before they are
mounted (in a shadow root, so a cell click can be traced) they are reduced to
table markup. Scripts, event handlers, links, embeds and `url(...)` are
removed.

It replaces `tlf-viewer.html` as the master's entry point. The TLF viewer
stays in `generate-ard-tlfs`, where the TLF reviewer uses it. It is also the
master's fallback when this workflow does not finish.

## Run locally

```bash
python3 artifacts/scripts/build_explorer.py <package dir> <output dir>   # <kind>/<name> layout, e.g. handover/e2e-a48c3201
```

Each script must stay ≤ 64 KiB (the carried-artifact cap). The HTML itself can
be several MB, mostly ARD and displays: about 6.7 MB for the CDISC pilot.

## Test

```bash
R_LIBS=$(Rscript -e 'cat(paste(.libPaths(),collapse=":"))') python3 tests/test_pipeline.py
```

The test uses a synthetic fixture. It checks that every table cell resolves
through ARD and ADaM to SDTM, that intermediate frames are traced to
`read_sdtm`, that a seeded broken `@derive` source, an unproduced planned
output and an unplanned objective each show up as a gap, that malformed tags
and lineage from a package that skipped the upstream gates become gaps rather
than crashes, and that CORE impact
reaches the output. It also checks that the page is self-contained, that
`resolve-inputs` and `build-explorer` run as steps, and that tampered files
fail verification.
