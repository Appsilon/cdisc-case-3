# generate-ard-tlfs

Generate the Analysis Results Data (ARD) and the rendered Tables, Listings and
Figures from ADaM and the approved specs, with every displayed number traced
back to the ARD. Part of the modular protocol-to-TFL set: runs on its own
(upload ADaM + specs) or inside a parent workflow (study package in the
trigger), after `specify-analyses` and `derive-adam`.

```
resolve-inputs ─needsUpload─► upload-inputs ─► stage-inputs ─► author-programs ─► execute-programs ─► reconcile ─► review-tlfs ─approve / spec-change─► return-result ─► done
       └──────── package ─────────────────────────┘                ▲                   │ needsFix          │ needsFix      │ revise
                                                                    ├──── retry ────────┴───────────────────┘               ▼
                                                                    └───────────────────────────────────────────────── record-review
                                                     needsFix, no attempts left ─► return-result (outcome failed)
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Package mode: picks `adam`, `analysis-spec.json`, `reporting-event.json` (kind `ars`), `tlf-plan.json`, and optionally `lineage` (`lineage.json`, and derive-adam's `population-counts.json`) and `tfl-program`. Missing pieces → fails (run specify-analyses / derive-adam first). Standalone: routes to the upload. |
| `upload-inputs` | human (`stat-programmer`) | ADaM `.xpt`, the three spec/plan JSON files by name; optionally `lineage.json`, `population-counts.json` and existing `.R` programs. |
| `stage-inputs` | script | sha256-verifies and stages under `/workspace/generate-ard-tlfs/inputs`; `adam-columns.json` (columns per ADaM dataset, via the shared `sdtminventory.py`); restores existing programs to `/workspace/tlf-programs`. |
| `author-programs` | **agent** | `tlf-generator` skill (carried): one R program per planned output with an analysis-spec entry, `# @tlf <final_id> analysis=<AN id> uses=<DS.VAR,...>`. Numbers into the ARD first (with one big-N row per column, and rows that say what they summarise), display rendered from the ARD. Runs `self_check.py` (all gates below) until PASS. |
| `execute-programs` | script | Each program in a fresh `Rscript --vanilla` against the staged ADaM: tag resolves (planned output, ARS analysis, ADaM variables that exist), clean exit, a well-formed ARD (`$ARD_DIR/<id>.json`) and display (`$TFL_DIR/<id>.html`, figures `<id>.png`). R warnings are counted, not fatal. |
| `reconcile` | script | Every table body cell that shows numbers (not the row label, not `<th>`-only header rows) names their ARD rows in `data-ard="i,j"` (0-based, one per number, in order); each number must equal exactly that row's stat rounded half away from zero at the shown precision (a proportion may show ×100 — always when followed by `%`; `<0.001` must bound it). Matching any other ARD value does not count — on large ARDs a wrong number usually equals some other statistic. Header cells showing `N=` are checked the same way. Listings show ADaM records, so only their cells that carry `data-ard` are checked. Then the **accuracy gates** (`accuracy.py` + the fixed `recompute.R`), see below. Builds `tlf-viewer.html`, `reconciliation.json` and `accuracy.json`. |
| `review-tlfs` | human review (`statistician`, `stat-programmer`) | Approve; request changes to the programs; or **spec-change** — the analysis itself is wrong. |
| `record-review` | script | Appends the comment to `review-feedback.jsonl` and resets the attempts (shared `gate.GateLoop`). |
| `return-result` | script | `generated` (publishes `ard`, `tfl` — displays, viewer, reconciliation, accuracy — `tfl-program`, `tfl-log`), `upstream_change` (the reviewer's `request` for the specs; viewer + programs attached, package unchanged), or `failed`. |

## The AI / deterministic boundary

The agent's only output is code. Every ARD, display and log comes from
`execute-programs`; `reconcile` proves that no displayed number was typed or
computed in the renderer. The program contract is the docstring of
`artifacts/scripts/tfllib.py`.

Reconciliation alone says nothing about whether the ARD is right (a run on the
wrong SDTM passed it with every number wrong), so `reconcile` also checks the
ARD against the data, with code that is not the agent's: `accuracy.py` reads the
ARS ReportingEvent (the output's analysis → analysis set, data subset, the
treatment grouping: the orderedGrouping whose variable is `TRT01P`/`TRT01A`/
`TRTP`/`TRTA`/`ARM`/`ACTARM`, in any position; `TRTP`/`TRTA` resolve to ADSL
`TRT01P`/`TRT01A`) and one fixed R
program, `recompute.R`, aggregates the staged ADaM (haven).

- **Denominators (gate 3).** Every table and figure ARD has one big-N row per
  column (`variable` `BIGN`, `stat_name` `N`, `group1_level` = arm or `Total`).
  Each must equal the ADSL subjects in the ARS analysis set for that arm; every
  arm with subjects needs one; the display must name each in a `data-ard` (the
  header `N=`, itself reconciled). An analysis grouped only by non-treatment
  variables has its big N *not checked*. Outputs whose analysis set cannot be
  evaluated must agree with outputs on the same ARS analysis set. With
  `population-counts.json` from derive-adam, the flag's total (and per-arm
  counts, when its `armVariable` is the grouping) is compared with ADSL; a
  difference is a **warning** (accuracy.json, the viewer, the step summary),
  not a problem for the agent: the ADaM was approved upstream.
- **Independent recompute (gate 4).** For analyses whose ARS method is a simple
  summary (descriptive / frequency / incidence / counts), every numeric ARD row
  is recomputed over analysis set + data subset + `group1..k` + the row's
  optional `filter` where-clause: `N` (non-missing subjects or records, or the
  arm's big N), `n` (subjects, or records; a `variable_level` of `""` or
  `Missing` counts the null / blank values), `p` / `pct` (n over the arm's big N
  or over N, fraction or ×100), `mean`, `sd`, `median`, `min`, `max`. A value
  matches within 1e-6 relative, within 5e-5 absolute, or when the recomputed
  value rounded to the ARD value's own decimals equals it (an ARD written at
  reduced precision; integer ARD values must be exact). A mismatch goes back to
  the agent, naming each reading the ADaM supports and what it counted, as does
  a row `filter` that is not an AND-only where-clause (the program's own
  contract).
- **Coverage, not silence.** Model-based methods (ANCOVA, MMRM, KM, shift, CMH,
  tests, listings), other statistics (LS means, CIs, p-values, quartiles), a
  `variable` or group that is not an ADaM column, and subsets that are not an
  AND of comparisons (`=`, `IN`, `IS [NOT] NULL`, `<`/`>`) are counted as *not
  independently checked*, never failed. `accuracy.json` and the viewer report
  "k of n ARD statistics recomputed" and the reasons for the rest.

## The viewer (`tlf-viewer.html`)

One self-contained page (no external requests, theme-aware): per output the
rendered table (sandboxed iframe; hover a cell for the ARD rows it was rendered from) or figure, the ARD rows (numbered), the program, and the
trace — ARS analysis, analysis set, record subset, methods, and each ADaM
variable the program reads, with the ADaM program lines and SDTM sources from
`lineage.json` when supplied.

## Test

```bash
R_LIBS=$(Rscript -e 'cat(paste(.libPaths(),collapse=":"))') python3 tests/test_pipeline.py    # needs R with haven, jsonlite, ggplot2
```

Real R on a 12-subject ADSL/ADAE: a table and a figure generated and
reconciled, big N recounted and all 12 ARD statistics recomputed; a typed-in
number, a bad `uses=` tag and a missing program sent back until `failed`; a
cell showing another arm's mean (in the ARD, wrong row) rejected; 5 SAFFL values
flipped in ADSL after the ARD was made, and a big N off by one in both ARD and
header, rejected by the denominator gate (population-counts.json disagreeing
only warns); an ARD mean shifted with the display rejected by the recompute
(reconcile alone passes both, the agent's self-check catches them); an ARD
written at jsonlite's default 4 decimals passes; a SEX grouping ordered before
treatment still checks big N by arm, a SEX-only grouping leaves it not checked;
upload mode with a review round,
then `upstream_change`; the cell checks alone (missing / miscounted /
out-of-range `data-ard`, an off-by-one digit that equals another ARD stat,
bounds, percentages, header N); the where-clause parser, what stays
unchecked, the rounding tolerance and `Missing` category rows. With the CDISC pilot ADSL present (`PILOT_ADSL`, default
`~/Repo/experimental-fda-submission-4-podman/submissions-pilot2/datasets/adam/adsl.xpt`,
254 subjects) the demographics program runs on it and passes; otherwise that
test is skipped.
