# ard-tfl-generation

Generate the Analysis Results Data (ARD) and the rendered Tables, Listings and
Figures from ADaM and the approved specs, with every displayed number traced
back to the ARD. Part of the modular protocol-to-TFL set: runs on its own
(upload ADaM + specs) or inside a parent workflow (study package in the
trigger), after `analysis-specification` and `adam-derivation`.

```
resolve-inputs ─needsUpload─► upload-inputs ─► stage-inputs ─► author-programs ─► execute-programs ─► reconcile ─► review-tlfs ─approve / spec-change─► return-result ─► done
       └──────── package ─────────────────────────┘                ▲                   │ needsFix          │ needsFix      │ revise
                                                                    ├──── retry ────────┴───────────────────┘               ▼
                                                                    └───────────────────────────────────────────────── record-review
                                                     needsFix, no attempts left ─► return-result (outcome failed)
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Package mode: picks `adam`, `analysis-spec.json`, `reporting-event.json` (kind `ars`), `tlf-plan.json`, and optionally `lineage` and `tfl-program`. Missing pieces → fails (run analysis-specification / adam-derivation first). Standalone: routes to the upload. |
| `upload-inputs` | human (`stat-programmer`) | ADaM `.xpt`, the three spec/plan JSON files by name; optionally `lineage.json` and existing `.R` programs. |
| `stage-inputs` | script | sha256-verifies and stages under `/workspace/ard-tfl-generation/inputs`; `adam-columns.json` (columns per ADaM dataset, via the shared `sdtminventory.py`); restores existing programs to `/workspace/tlf-programs`. |
| `author-programs` | **agent** | `tlf-generator` skill (carried): one R program per planned output with an analysis-spec entry, `# @tlf <final_id> analysis=<AN id> uses=<DS.VAR,...>`. Numbers into the ARD first, display rendered from the ARD. Runs `self_check.py` until PASS. |
| `execute-programs` | script | Each program in a fresh `Rscript --vanilla` against the staged ADaM: tag resolves (planned output, ARS analysis, ADaM variables that exist), clean exit, a well-formed ARD (`$ARD_DIR/<id>.json`) and display (`$TFL_DIR/<id>.html`, figures `<id>.png`). R warnings are counted, not fatal. |
| `reconcile` | script | Every table body cell that shows numbers (not the row label, not `<th>`-only header rows) names their ARD rows in `data-ard="i,j"` (0-based, one per number, in order); each number must equal exactly that row's stat rounded half away from zero at the shown precision (a proportion may show ×100 — always when followed by `%`; `<0.001` must bound it). Matching any other ARD value does not count — on large ARDs a wrong number usually equals some other statistic. Listings show ADaM records, so only their cells that carry `data-ard` are checked. Builds `tlf-viewer.html` and `reconciliation.json`. |
| `review-tlfs` | human review (`statistician`, `stat-programmer`) | Approve; request changes to the programs; or **spec-change** — the analysis itself is wrong. |
| `record-review` | script | Appends the comment to `review-feedback.jsonl` and resets the attempts (shared `gate.GateLoop`). |
| `return-result` | script | `generated` (publishes `ard`, `tfl` — displays, viewer, reconciliation — `tfl-program`, `tfl-log`), `upstream_change` (the reviewer's `request` for the specs; viewer + programs attached, package unchanged), or `failed`. |

## The AI / deterministic boundary

The agent's only output is code. Every ARD, display and log comes from
`execute-programs`; `reconcile` proves that no displayed number was typed or
computed in the renderer. The program contract is the docstring of
`artifacts/scripts/tfllib.py`.

## The viewer (`tlf-viewer.html`)

One self-contained page (no external requests, theme-aware): per output the
rendered table (sandboxed iframe; hover a cell for the ARD rows it was rendered from) or figure, the ARD rows (numbered), the program, and the
trace — ARS analysis, analysis set, record subset, methods, and each ADaM
variable the program reads, with the ADaM program lines and SDTM sources from
`lineage.json` when supplied.

## Test

```bash
python3 tests/test_pipeline.py    # needs R with haven, jsonlite, ggplot2
```

Real R on a 12-subject ADSL/ADAE: a table and a figure generated and
reconciled; a typed-in number, a bad `uses=` tag and a missing program sent
back until `failed`; a cell showing another arm's mean (in the ARD, wrong row)
rejected; upload mode with a review round, then `upstream_change`; and the cell
checks alone (missing / miscounted / out-of-range `data-ard`, an off-by-one digit
that equals another ARD stat, bounds, percentages).
