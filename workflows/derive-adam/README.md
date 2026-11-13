# derive-adam

Derive the ADaM datasets an ADaM spec demands from SDTM, with every variable
traced to the program lines that make it. Part of the modular protocol-to-TFL
set: runs on its own (upload SDTM + `adam-spec.json`) or inside a parent
workflow (study package in the trigger), including the fix loop after a
rejected ADaM validation by `validate-with-core`.

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
| `stage-inputs` | script | sha256-verifies inputs (never falls back to other data), stages them under `/workspace/derive-adam/inputs`, and on a fix loop restores the programs and writes `core-findings.json`: the findings marked `fix` that the latest CORE report still shows, with example records. |
| `author-programs` | **agent** | Writes `/workspace/programs/<dataset>.R` with `@derive` tags (skill: `artifacts/skill/SKILL.md`). Runs `self_check.py` (the same gates, no attempt used) until PASS. Writes code only. |
| `execute-programs` | script | Each program in a fresh `Rscript --vanilla`, `@depends` order, staged SDTM only. Fails on ERROR/WARNING in a log, missing labels, columns SAS V5 cannot hold. Publishes `adam/*.xpt`, `logs/`, `programs/` (exactly what ran). |
| `check-lineage` | script | `lineage.json` from the tags; fails unless every column has exactly one tag, the tagged block mentions the variable, every `src=` exists, and every spec dataset/variable/PARAMCD was produced. Then the **ADaM conservation** checks (`populations.py`, below), which write `population-counts.json`. |
| `generate-define` | script | Define-XML 2.1 from the executed datasets and lineage; one MethodDef per derived variable naming its program lines. |
| `return-result` | script | `outcome` `derived` (publishes `adam`, `adam-program`, `adam-log`, `lineage` (`lineage.json` + `population-counts.json`), `adam-define`) or `failed` (programs + logs only; package data unchanged). |

The AI/deterministic boundary: the agent's output is code. Every dataset, log,
lineage entry and define item comes from the script steps.

Attempts: `execute-programs` counts one attempt per run of the programs; a gate
failure returns to the agent while `attempt < 3`, so at most three attempts in
total (two returns), then `failed`. The agent sees the gate's problems in
`/workspace/derive-adam/feedback.json`.

## Program contract and tags

See `artifacts/scripts/adamlib.py` (docstring) and `artifacts/skill/SKILL.md`:

```r
# @derive ADSL.TRTSDT origin=Derived src=EX.EXSTDTC,EX.EXDOSE method="Date of the first exposure with EXDOSE >= 0 (placebo 0 counts)"
# @derive ADSL.AGE,ADSL.SEX origin=Predecessor src=DM.*
```

`lineage.json` (consumed by `validate-with-core` to trace findings to code):

```json
{"variables": [{"dataset": "ADSL", "variable": "TRTSDT", "origin": "Derived", "program": "adsl.R",
                "lines": [19, 21], "spec": "ADSL.TRTSDT", "sources": ["EX.EXSTDTC", "EX.EXDOSE"], "method": "..."}],
 "consumers": {"ADSL.TRTSDT": ["T-14.3.1"]}}
```

Lines are 1-based and inclusive; `consumers` comes from the spec's `used_by_tables`.

## ADaM conservation (populations)

`check-lineage` also re-reads DM, EX and the exported `.xpt` (R haven) and
checks the ADaM against the SDTM it came from, independent of the agent's code.
A difference fails the attempt and goes back to the agent with the subjects named:

- ADSL subjects = all DM subjects, or exactly the randomised ones (DM minus
  `ARMCD`/`ARM` like `Scrnfail`, `Screen Failure`, `NOTASSGN`, `Not Assigned`, any
  case, or both blank; one definition, `workflows/shared/arms.py`); one record per
  subject.
- `SAFFL='Y'` = subjects with an EX record with `EXSTDTC` (any `EXDOSE`: pilot
  placebo is `EXDOSE = 0`).
- `RANDFL` / `ITTFL` = 'Y' (whichever exist) = the randomised subjects.
- Over the randomised subjects `TRT01P` maps one-to-one onto `DM.ARM`; over the
  treated ones (`ACTARM` also not `Not Treated` / `Unplanned Treatment`) `TRT01A`
  onto `DM.ACTARM`, with a note naming the subjects whose `ACTARM` ≠ `ARM`. A
  `TRT01A` that maps onto `DM.ARM` instead passes with a note in the step's `notes`:
  the CDISC pilot ADSL sets `TRT01A = TRT01P`, although 12 subjects have
  `ACTARM` ≠ `ARM`.
- Every `USUBJID` of every other ADaM dataset is in ADSL.

These are the gate's definitions: a study whose ITTFL means "randomised and
dosed" (mITT) fails it and needs the rule widened here first. R failing, or
an unreadable staged DM / EX, fails the step (infrastructure, not the agent's);
an ADaM `.xpt` that haven cannot read goes back to the agent.

`population-counts.json` (step output `populations`, published under kind
`lineage` so no new package kind is needed) counts every ADSL `*FL` flag that
has a `Y`, by `TRT01A` (else `TRT01P`). generate-ard-tlfs stages it and
compares it with the ADSL its big Ns are recounted from (a difference is a
warning there):

```json
{"datasets": {"ADSL": {"records": 254}, "ADADAS": {"records": 12463}},
 "populations": {"SAFFL": {"total": 254, "byArm": {"Placebo": 86, "Xanomeline High Dose": 84, "Xanomeline Low Dose": 84}}},
 "armVariable": "TRT01A"}
```

## Image

All steps use the catalog image `mediforce-built:5d4c205d6727` (R + admiral +
haven/xportr + Python, the one UC3 runs on), so the agent tests in the same R
the executor uses. Scripts and the skill are carried artifacts (`/artifacts`).

## Not yet

- Record-level trace: BDS/OCCDS `SRCDOM`/`SRCVAR`/`SRCSEQ` are not required or
  gated yet (the CORE report shows them when present).
- `src=` is checked for existence, not against what the block reads.
- Per-PARAMCD record counts against the source SDTM records are not checked
  (no declared filter to compare with).

## Test

```bash
R_LIBS=$(Rscript -e 'cat(paste(.libPaths(),collapse=":"))') python3 tests/test_pipeline.py
```

Real R, real CDISC pilot SDTM (`SDTM_DIR`, default
`~/Repo/protocol-to-tfl/test-docs/cdiscpilot01/sdtm`); `tests/fixtures/programs`
stand in for the agent. Covers upload mode, fix-loop staging (stale and orphaned
findings), a clean derivation (lineage, define, population counts, package
kinds), retry → `failed`, and the population gate's seeded defects: the pilot's
own ADaM (`PILOT_ADAM_DIR`, default
`~/Repo/experimental-fda-submission-4-podman/submissions-pilot2/datasets/adam`)
passes; 5 flipped `SAFFL`, a dropped ADSL subject, 3 swapped `TRT01P` and an
ADSL from the 18-subject synthetic SDTM (`SYNTHETIC_SDTM_DIR`, default
`~/Repo/FULL_WORKFLOW/inputs/sdtm`) fail; upper-case `SCRNFAIL`, `Unplanned
Treatment` and an `ACTARM` ≠ `ARM` subject pass (the last with a note); an
unreadable ADaM `.xpt` goes back to the agent, an unreadable DM fails the step; a
flipped `SAFFL` in the programs goes back to the agent. The seeded-defect checks are skipped when those folders are
missing.
