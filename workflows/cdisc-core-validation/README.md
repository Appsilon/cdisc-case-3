# cdisc-core-validation

Validate SDTM, SEND, ADaM or USDM with the CDISC CORE rules engine and review
every finding in one place. Part of the modular protocol-to-TFL set: it runs on
its own (upload datasets) or as a checkpoint inside a parent workflow (study
package in the trigger) — the same definition serves the SDTM and the ADaM
checkpoints.

```
resolve-inputs ─needsUpload─► upload-datasets ─► run-core ─► build-report ─needsReview─► review-dispositions ─► decide ─► done
       └──────────── package ─────────────────────────┘             └────── no findings ──────────────────────┘    │
                                                         upload-datasets ◄── rejected && onReject == reupload ─────┘
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Package mode: picks files by `kind`. Standalone: routes to the upload. Fixes standard, version, CT, `onReject`. |
| `upload-datasets` | human (`data-manager`) | `.xpt`, `.sas7bdat`, Dataset-JSON, CSV, one `define.xml`, optional `lineage.json` + programs, sponsor rules `.yml`, `core-policy.json`. |
| `run-core` | script | sha256-verifies inputs, stages SAS V5 `.xpt`, runs CORE: published rules, then local rules (`-lr` replaces published rules, so it is a second pass). Issue rows are capped at 1,000 per rule × dataset (`-me 1000 true`): the real CDISC pilot raises 293k rows (CORE-000701 EPOCH missing on every QS/LB record), whose XLSX did not finish within an hour on prod; CORE's `Issue_Summary` keeps the true counts. `run-core` asks for `script.resources` 16g / 4 CPUs (mediforce ≥ PR #1671, granted up to the deployment's `SCRIPT_MAX_MEMORY` / `SCRIPT_MAX_CPUS`; older platforms ignore the field and run it in 8 GB / 2 CPUs). CORE sizes its caches (and picks pandas vs Dask) from psutil's free memory, which in a container is the **host's**; `core_memory/sitecustomize.py` (on CORE's `PYTHONPATH`) makes every CORE process see half the container's usable memory instead. CORE is forced onto pandas (`DATASET_SIZE_THRESHOLD`): its Dask path was 3× slower on the pilot **and reported different findings** (163k vs 293k issues). Workers = available CPUs (cgroup quota), at most one per 4 GB left after the caches (`CORE_POOL_SIZE` overrides) — one worker plus caches peaked at 6.7 GB on the pilot (CORE-002123 on QS); a worker killed by the kernel makes CORE's pool hang (locally); on prod v4–v6 `run-core` died with "job stalled" after ~5 min. **CORE-000206 is replaced** by the carried `rules/sdtmig/CORE-000206.yml`: CORE v1.0.0 publishes it matching SUPP/CO/RELREC to the parent on USUBJID only, a per-subject cross join that raised 8,408 false issues on the pilot's clean SUPPAE and needed >14 GB on SUPPLB. The carried file is CDISC's corrected definition (keys USUBJID, IDVAR, IDVARVAL, as in later CORE releases): 0 issues on the clean pilot, exactly the 2 seeded bad IDVARVALs. Generally, a local rule whose `Core.Id` is a published `CORE-*` id replaces that rule (`-er` on the published pass, noted in the result). The result's `environment` records CPUs, memory, worker count and seconds per pass. Each pass is watched every 30 s (CORE `-p verbose_output` logs one line per finished rule): a kernel OOM kill in the container, or the step's 110-min budget running out, stops CORE and fails the step with how far it got ("N rule(s) finished, last CORE-…") — the platform shows no output of a running script step, and CORE's pool would otherwise wait forever for a killed worker. Staging folders are emptied first, so a retried step starts clean. Timeout 120 min. |
| `build-report` | script | `core-report.html`, `core-issue-index-<std>.json`, one review row per rule × dataset. Issue counts come from CORE's summary; a capped group shows subjects as `≥n` and no new/fixed change (only its first 1,000 rows are known). |
| `review-dispositions` | human (`standards-reviewer`) | table-editor: Fix required (default) / Justified / False positive + justification. |
| `decide` | script | Any `fix` → `rejected`, else `accepted`. Merges dispositions, returns `{outcome, onReject, files, package}`. |

No AI step: every result comes from CORE and deterministic scripts.

## Trigger input

| Field | Default | Meaning |
|---|---|---|
| `package` | `{}` | Study package (`../shared/mfpkg.py`). Empty → upload mode. |
| `standard` | `sdtmig` | `sdtmig`, `adamig`, `sendig`, `usdm`. |
| `version` | `""` | CORE dash format (`3-4`, `1-3`). Empty → package `profile[standard]`, else newest. |
| `ct` | `""` | e.g. `sdtmct-2025-09-26`. Empty → profile `ct`, else the define's, else none. |
| `onReject` | `auto` | `reupload` (ask for corrected files in this run) or `return` (end rejected so the parent regenerates). `auto`: reupload standalone, return with a package. |

Every optional field has a default on purpose: `stepParams` fail the step on a
`${triggerPayload.x}` the run does not have, and the platform fills declared
defaults on every start path (manual, spawn, cron).

## Package kinds read and written

Reads, per standard: `sdtm`/`sdtm-define`, `adam`/`adam-define`, `send`/`send-define`,
`usdm`; plus `lineage`, `adam-program`, `core-policy`, `core-rules`,
`core-dispositions-<std>`, `core-issue-index-<std>`.
Writes: `core-report-<std>` (html, json, xlsx), `core-issue-index-<std>`,
`core-dispositions-<std>`; in upload mode also the uploaded data files.

## Traceability

`lineage.json` (written by `adam-derivation`):

```json
{
  "variables": [{"dataset": "ADSL", "variable": "TRTSDT", "origin": "Derived", "program": "adsl.R",
                 "lines": [40, 52], "spec": "ADSL.TRTSDT", "sources": ["EX.EXSTDTC"], "method": "optional"}],
  "consumers": {"ADSL.TRTSDT": ["T-14.3.1"]}
}
```

- ADaM finding → variable → program lines (snippet embedded) → spec entry → SDTM
  sources → TLFs that use it; BDS/OCCDS rows also show `SRCDOM.SRCVAR seq SRCSEQ`.
- SDTM finding → the ADaM variables derived from it and their TLFs (impact).
- CORE `row` is 1-based (verified against `AESEQ`).
- Issue identity is `core_id|dataset|USUBJID|SEQ-or-row`, so a re-validation reports
  new / fixed per finding; dispositions are keyed `core_id|dataset`.

## ADaM rules

CORE v1.0.0 lists `adamig` rule sets but publishes **no** ADaMIG rules (it aborts
with "No rules were selected"). `artifacts/rules/adamig/MF-ADAM-*.yml` fill the
gap; regenerate with `python3 tools/generate_adam_rules.py`. Each was checked:
SUCCESS on clean pilot ADaM, fires on a seeded defect. Sponsors add rules by
uploading `.yml` or putting `kind: core-rules` files in the package.

## SDTMIG rule fixes

`artifacts/rules/sdtmig/CORE-000206.yml` replaces CORE v1.0.0's published
CORE-000206 (IDVARVAL must be a value of IDVAR in RDOMAIN). v1.0.0 matches the
parent on USUBJID only: 8,408 false issues on the pilot's clean SUPPAE, and the
cross join with LB needs >14 GB for SUPPLB. The carried file is CDISC's later
definition (keys USUBJID, IDVAR, IDVARVAL). Checked with v1.0.0: SUCCESS on the
clean pilot SUPPAE/SUPPDS/SUPPDM, exactly 2 issues for 2 seeded bad IDVARVALs.

## Known CORE behaviour

- `CORE-002084` (FDA TRC1736b, "Missing Define-XML document") and `CORE-002056`
  are study-level checks reported on every row of one dataset, and which
  dataset depends on directory order (FT on Linux). They fire even with a
  Define-XML 2.1 supplied — disposition them, don't chase them.
- `-lr` replaces the published rules, hence two passes.

## Build, test, register

```bash
python3 tools/build_workflows.py cdisc-core-validation          # → dist/cdisc-core-validation.wd.json
CORE_HOME=<core release dir> SDTM_DIR=<sdtm> ADAM_DIR=<adam> \
  python3 workflows/cdisc-core-validation/tests/test_pipeline.py  # real CORE, all four scripts
pnpm exec mediforce workflow register --file=<abs>/dist/cdisc-core-validation.wd.json --namespace=<ns>
```

The image is built by the platform from the carried `artifacts/Dockerfile`
(python:3.12-slim + CORE v1.0.0 ubuntu-22.04 build; `core version` runs at build
time). Scripts run from `/artifacts/scripts`; no repo, commit or token needed.
