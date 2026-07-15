# Traceability graph — data model & HTML constraints

This documents the JSON model the explorer consumes and the hard constraints on the emitted HTML, so
the page **regenerates for any study**, not just CDISCPILOT01. The assembler builds one object and
embeds it verbatim in `<script id="graph-data" type="application/json">…</script>`.

## Top-level object

```jsonc
{
  "study":  { "id", "name", "title", "phase" },
  "counts": { "objectives", "endpoints", "endpoints_unresolved",
              "sdtm", "sdtm_absent", "adam", "tlf", "tlf_producible" },
  "status": { "generated", "blocked", "needs-clarification" },  // TLF tallies
  "issues": [ Issue, … ],   // aggregated problem feed (see "Issues feed")
  "nodes":  [ Node, … ],
  "edges":  [ Edge, … ]
}
```

## Issues feed

A first-class, **data-derived** list of everything a reviewer should be warned about. Built in
Workflow step 5 — **never hard-code a node's message in the JS**; every message comes from the
artifacts, so it generalizes to any study.

```jsonc
{
  "severity":       "blocked",              // blocked | clarification | gap | info
  "message":        "Domain DV is absent from the SDTM inventory; the Protocol Deviations listing cannot be built.",
  "nodeId":         "tlf:reg-protocol-deviations",  // the primary node this issue is about
  "relatedNodeIds": ["sdtm:DV"]             // other nodes to co-highlight (optional)
}
```

Sources (all from data already read — do not invent):
- **blocked** — each TLF with `status=="blocked"`; `message` = its `status_reason`; `nodeId` = the
  TLF; `relatedNodeIds` = the `absent` SDTM domain(s) it needs.
- **clarification** — each TLF with `status=="needs-clarification"`, and each unresolved endpoint
  (`resolved:false` / listed in `unresolved_endpoints`); `message` = `status_reason` / the placeholder.
- **gap** (coverage) — any Objective or resolved Endpoint with **no** downstream TLF.
- **info** — optional lines parsed from `issues.md` (data-quality / provenance notes), if present.

Every node referenced by an issue renders an on-graph **warning marker** (icon + label, from the
reserved status palette — never color alone). The UI derives markers from this array by `nodeId`, and
the Issues panel lists each entry as a row that focuses/pans to `nodeId` and highlights its lineage.

## Node

```jsonc
{
  "id":       "obj:Objective_1",       // "<typePrefix>:<sourceId>" — globally unique
  "type":     "Objective",             // Objective | Endpoint | Regulatory | TLF | ADaM | SDTM
  "tier":     0,                        // layout column (see tiers below)
  "label":    "END1",                  // short id/code chip shown in the node (mono)
  "sublabel": "ADAS-Cog(11) · Wk24",   // meaningful descriptor (see "Node labels") — NOT just the level
  "title":    "Alzheimer's … [ADAS-Cog (11)] at Week 24",  // full human text (panel + hover tooltip + search)
  "status":   "generated",             // TLF only: generated|blocked|needs-clarification
  "unresolved": false,                  // endpoint with placeholder text, or unplanned TLF
  "absent":   false,                    // SDTM domain required but not in inventory
  "isFigure": false,                    // TLF that is a Figure (e.g. Kaplan-Meier)
  "meta":     { … }                     // type-specific payload (see below)
}
```

`id` prefixes: `obj:`, `end:`, `reg:`, `tlf:`, `adam:`, `sdtm:`. TLF node ids use the **candidate_id**
(`tlf:eff-END1-ancova-wk24-locf`) so unplanned candidates without a `final_id` still get a stable id.

### `meta` by type
- **Objective** — `level`, `description`, `text`, `endpoints[]` (endpoint ids).
- **Endpoint** — `level`, `text`, `objective` (id), `resolved`, `measure`, `measure_type`,
  `timepoints[]`, `domain_hint`.
- **Regulatory** — `standard` ("ICH E3"), `note`. A single shared source node for scaffolding outputs.
- **TLF** — `candidate_id`, `final_id`, `dir_id`, `type`, `category`, `cat_label`, `title`, `status`,
  `status_reason`, `priority`, `produced_by`, `notes[]`, `method`, `population`, `timepoint`,
  `imputation`, `subgroup`, `comparison`, `objectives[]`, `endpoints[]`, `regulatory_rule`, `adam[]`,
  `sdtm[]`, `analysisSet`, `analysisSetCond`, `dataSubset`, `purpose`, and embedded raw content
  `generatedMd`, `ardJson`, `generateR`, `generateRPath`, `isFigure`.
- **ADaM** — `klass`, `sdtm_source[]` (domains), `used_by_tables[]`, `derivation_requirements[]`,
  `parameters[] = {paramcd, param, note}`, and
  `variables[] = {name, role, source_domains[]}` — where `source_domains[]` is the subset of the
  dataset's `sdtm_source` that this variable draws from (inferred from `sdtm_source` + any domain
  named in the `role`/derivation text; `[]` or `["*"]` when not determinable). These power the ADaM
  panel's Variables/Parameters tables and the optional variable sub-nodes.
- **SDTM** — `domain`, `label`, `absent`. The panel shows a reverse view: which ADaM datasets /
  variables consume this domain (from ADaM `sdtm_source` / `variables[].source_domains`).

### Node labels (the node face)

`label` is the stable mono **code chip** (`OBJ1`, `END1`, `T-14-3.01`, `ADQSADAS`, `QS`, `ICH E3`).
`sublabel` must be a **meaningful, human-readable descriptor** — the reader should understand a node
without opening the panel. Derive it per type, and always keep the full text in `title` (panel +
hover `<title>` tooltip):

| type | `sublabel` derivation | fallback |
|---|---|---|
| Endpoint | `meta.measure` + short timepoint, e.g. `"ADAS-Cog(11) · Wk24"` (join multiple timepoints with `/`) | `meta.text` truncated → `meta.level` |
| Objective | concise phrase from `meta.text` (first clause), or the distinct child-endpoint measures, e.g. `"ADAS-Cog(11) & CIBIC+ vs dose"` | `meta.text` truncated → `meta.level` |
| TLF | `meta.title` / `cat_label` (already meaningful) | `meta.type` |
| ADaM | `meta.klass` (e.g. `BDS`) | dataset name |
| SDTM | `meta.label` (domain label) | `meta.domain` |
| Regulatory | `meta.standard` (e.g. `ICH E3`) | — |

`level` (Primary/Secondary) moves to a small tag/tint, no longer the whole caption. Truncate long
sublabels with an ellipsis; the tooltip and panel carry the full string.

## Edge

```jsonc
{ "source": "<nodeId>", "target": "<nodeId>", "kind": "end-tlf", "dashed": false, "rule": null }
```

| kind | direction | source | built from |
|---|---|---|---|
| `obj-end`   | Objective → Endpoint | study-model `objectives[].endpoint_ids` |
| `end-tlf`   | Endpoint → TLF | tlf-plan `traces_to.endpoint_ids` |
| `reg-tlf`   | Regulatory → TLF | tlf-plan `traces_to.regulatory_rule` (rule stored on edge) |
| `tlf-adam`  | TLF → ADaM | adam-spec `datasets[].used_by_tables` (authoritative); fall back to tlf-plan `data_requirements.adam` for unplanned tables |
| `adam-sdtm` | ADaM → SDTM | adam-spec `datasets[].sdtm_source` |
| `tlf-sdtm`  | TLF → SDTM (**dashed**) | only when a table *declares* an SDTM source but has **no** ADaM bridge to it (blocked/clarify) — "declared, not derived" |
| `var-sdtm`  | ADaM-variable → SDTM domain | a variable's `source_domains[]`; emitted **only** while an ADaM node is expanded (see "Variable sub-nodes") |

All edges flow left→right in tier order, so the graph is a legible near-DAG.

## Variable sub-nodes (drill-down)

Variable-level ADaM↔SDTM traceability is a **drill-down**, not part of the default graph — the hero
view stays at entity level so it remains legible. Two surfaces, both driven by ADaM `meta.variables[]`
/ `meta.parameters[]`:

1. **Detail panels (always available).** The ADaM panel renders a **Variables** table
   (`name` · `role`/derivation · `source_domains`) and a **Parameters** table (`paramcd` · `param` ·
   `note`) — scrollable/expandable, not truncated. The SDTM panel renders the reverse: the ADaM
   datasets/variables that consume this domain.
2. **On-graph expansion (opt-in).** Clicking an ADaM node's expand affordance spawns transient
   **variable sub-nodes** (`id` = `adamvar:<DATASET>.<VAR>`, `type` `ADaMVar`, `meta.role`) beside the
   dataset, each joined to its `source_domains` by a `var-sdtm` edge. Collapsing removes them. Sub-nodes
   are generated from `meta.variables[]` at render time — they are **not** stored in the base
   `nodes[]`/`edges[]`, so the persisted model and its counts are unchanged.

> Deeper still (future): authoritative per-variable origin (`define.xml` Predecessor/Derived/Assigned
> → the exact source SDTM variable + controlled terminology). That needs `define.xml` wired as an
> input and XML parsing; the current pass uses the ADaM spec only.

## Tiers (layout)

| tier | column | types |
|---|---|---|
| 0 | Objective | Objective |
| 1 | Endpoint / Reg. | Endpoint + the single Regulatory node (Regulatory placed first) |
| 2 | Deliverable (TLF) | TLF / Figure — the tallest column, the focal center |
| 3 | ADaM dataset | ADaM |
| 4 | SDTM domain | SDTM (present + any `absent` required domain) |

Layered layout: `x = MX + tier*COL`; within a tier, stack by a stable order and vertically center each
tier's block against the tallest column. Initial view fits the world box to the viewport. Nodes are
draggable; pan/zoom is a single `translate()+scale()` transform on the root `<g>`.

## Status model

Badges come from the **plan** (`status` / `status_reason` in `tlf-plan.json`) and whether the TLF's
outputs exist — never from re-diffing or a scorecard:
`✅ generated` (a `.generated.md` was produced) · `⛔ blocked` (a required derivation/domain is
absent) · `❓ needs-clarification` (traces to an unresolved endpoint). Non-TLF nodes carry no status;
a status **filter** hides TLFs of a given status and dims upstream/data nodes that lose all visible
connections.

## Lineage traversal (highlight rule)

Selecting a node highlights its **directed** lineage — *ancestors* (walk `edges` backward) ∪
*descendants* (walk forward) ∪ self — and dims the rest. This is deliberately **not** the undirected
connected component: a shared dataset like `ADSL` would otherwise pull in the whole graph. From a TLF
this yields the clean slice `Objective → Endpoint/Reg → TLF → ADaM → SDTM`; from an ADaM node it
yields "everything this dataset feeds." The panel breadcrumb renders the same lineage in reading order
`OBJ ▸ END ▸ SDTM ▸ ADaM ▸ TLF`.

## Self-contained HTML / CSP constraints (hard requirements)

The file must open offline and publish as a claude.ai Artifact, which enforces a strict CSP:

- **No external requests of any kind** — no `<script src>`, no `<link rel=stylesheet>`, no `@import`,
  no CDN, no web fonts, no remote images, no `fetch`/XHR/WebSocket. Inline all CSS and JS; use
  `system-ui` + a monospace stack (no downloaded faces); embed any raster as a `data:` URI.
- **Data embedded inline** as `<script type="application/json">`. When serializing, escape `</` as
  `<\/` so embedded `generate.R` / markdown / ARD can't terminate the script element early.
- **Graphics are vanilla SVG** built with `createElementNS`; no D3 or graph library.
- **Theme-aware**: default to `prefers-color-scheme`, plus a toggle that stamps `data-theme` on the
  root (the toggle must win both ways). Define colors as CSS custom properties so light/dark swap in
  one place.
- **Responsive**: the page body never scrolls horizontally; wide content (rendered tables, ARD, code)
  scrolls inside its own `overflow:auto` container. Respect `prefers-reduced-motion`.

## Palette (categorical, validated)

Node identity uses dataviz categorical slots 1–5 in graph-chain order (validated for CVD in both
modes); the lone Regulatory node uses an intentional neutral slate (secondary-encoded by position and
a dashed/neutral treatment). Status uses the **reserved** status palette, never a categorical slot.

| Type | Light | Dark |
|---|---|---|
| Objective | `#2a78d6` | `#3987e5` |
| Endpoint  | `#1baf7a` | `#199e70` |
| TLF       | `#eda100` | `#e0a836` |
| ADaM      | `#008300` | `#3ca63c` |
| SDTM      | `#4a3aa7` | `#9085e9` |
| Regulatory| `#64748b` | `#8b98ad` |

Because two categorical fills sit below 3:1 on the light surface, identity is reinforced by an ink
label, a solid color rail on each node, and per-type filter legend chips (the "relief rule") — color
is never the sole channel.

## Drill-down hooks

The default graph is entity-level; depth is layered on without reshaping the base model:
- **Variable level (this pass)** — ADaM `meta.variables[]`/`parameters[]` power the panel tables and
  opt-in `ADaMVar` sub-nodes + `var-sdtm` edges (see "Variable sub-nodes"). Generated at render time;
  not persisted in `nodes[]`/`edges[]`.
- **Cell → ARD (future)** — the TLF `meta` already carries `ardJson`; a cell click can look up the
  matching ARD record and open a sub-panel, again with no change to the node/edge model.
