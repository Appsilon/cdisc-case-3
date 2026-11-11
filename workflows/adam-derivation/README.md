# adam-derivation

Derive the ADaM datasets an ADaM spec demands from SDTM, with every variable
traced to the program lines that make it. Part of the modular protocol-to-TFL
set: runs on its own (upload SDTM + `adam-spec.json`) or inside a parent
workflow (study package in the trigger), including the fix loop after a
rejected ADaM validation by `cdisc-core-validation`.

```
resolve-inputs ─needsUpload─► upload-inputs ─► stage-inputs ─► author-programs ─► execute-programs ─► check-lineage ─► generate-define ─► return-result ─► done
       └──────── package ──────────────────────────┘                ▲                   │ needsFix          │ needsFix
                                                                    └──── retry ────────┴───────────────────┘
                                                      needsFix, no attempts left ─► return-result (outcome failed)
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Package mode: picks `sdtm`, `adam-spec`, `sdtm-define`, `analysis-spec`, and on a fix loop `adam-program`, `lineage`, `core-dispositions-adamig`, `core-report.json`. Standalone: routes to the upload. |
| `upload-inputs` | human (`adam-programmer`) | SDTM `.xpt`/`.sas7bdat`, `adam-spec.json`, optional define, analysis spec, previous programs + CORE files. |
| `stage-inputs` | script | sha256-verifies inputs (never falls back to other data), stages them under `/workspace/adam-derivation/inputs`, and on a fix loop restores the programs and writes `core-findings.json`: the findings marked `fix` that the latest CORE report still shows, with example records. |
| `author-programs` | **agent** | Writes `/workspace/programs/<dataset>.R` with `@derive` tags (skill: `artifacts/skill/SKILL.md`). Runs `self_check.py` (the same gates, no attempt used) until PASS. Writes code only. |
| `execute-programs` | script | Each program in a fresh `Rscript --vanilla`, `@depends` order, staged SDTM only. Fails on ERROR/WARNING in a log, missing labels, columns SAS V5 cannot hold. Publishes `adam/*.xpt`, `logs/`, `programs/` (exactly what ran). |
| `check-lineage` | script | `lineage.json` from the tags; fails unless every column has exactly one tag, the tagged block mentions the variable, every `src=` exists, and every spec dataset/variable/PARAMCD was produced. |
| `generate-define` | script | Define-XML 2.1 from the executed datasets and lineage; one MethodDef per derived variable naming its program lines. |
| `return-result` | script | `outcome` `derived` (publishes `adam`, `adam-program`, `adam-log`, `lineage`, `adam-define`) or `failed` (programs + logs only; package data unchanged). |

The AI/deterministic boundary: the agent's output is code. Every dataset, log,
lineage entry and define item comes from the script steps.

Attempts: `execute-programs` counts one attempt per run of the programs; a gate
failure returns to the agent while `attempt < 3`, so at most three attempts in
total (two returns), then `failed`. The agent sees the gate's problems in
`/workspace/adam-derivation/feedback.json`.

## Program contract and tags

See `artifacts/scripts/adamlib.py` (docstring) and `artifacts/skill/SKILL.md`:

```r
# @derive ADSL.TRTSDT origin=Derived src=EX.EXSTDTC,EX.EXDOSE method="Date of the first exposure with EXDOSE > 0"
# @derive ADSL.AGE,ADSL.SEX origin=Predecessor src=DM.*
```

`lineage.json` (consumed by `cdisc-core-validation` to trace findings to code):

```json
{"variables": [{"dataset": "ADSL", "variable": "TRTSDT", "origin": "Derived", "program": "adsl.R",
                "lines": [19, 21], "spec": "ADSL.TRTSDT", "sources": ["EX.EXSTDTC", "EX.EXDOSE"], "method": "..."}],
 "consumers": {"ADSL.TRTSDT": ["T-14.3.1"]}}
```

Lines are 1-based and inclusive; `consumers` comes from the spec's `used_by_tables`.

## Image

All steps use the catalog image `mediforce-built:5d4c205d6727` (R + admiral +
haven/xportr + Python, the one UC3 runs on), so the agent tests in the same R
the executor uses. Scripts and the skill are carried artifacts (`/artifacts`).

## Not yet

- Record-level trace: BDS/OCCDS `SRCDOM`/`SRCVAR`/`SRCSEQ` are not required or
  gated yet (the CORE report shows them when present).
- `src=` is checked for existence, not against what the block reads.

## Test

```bash
SDTM_DIR=$HOME/Repo/FULL_WORKFLOW/inputs/sdtm python3 tests/test_pipeline.py
```

Real R, real SDTM; `tests/fixtures/programs` stand in for the agent. Covers
upload mode, fix-loop staging (stale and orphaned findings), a clean
derivation (lineage, define, package kinds) and retry → `failed`.
