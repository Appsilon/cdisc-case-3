# analysis-specification

Turn an approved TLF plan into the specifications that drive computation. Part
of the modular protocol-to-TFL set: runs on its own (upload the plan) or inside
a parent workflow (study package in the trigger), between `tlf-planning` and
`adam-derivation` / `ard-tfl-generation`.

```
resolve-inputs ─needsUpload─► upload-inputs ─► stage-inputs ─► build-specs ─► check-specs ─► review-specs ─approve─► return-result ─► done
       └──────── package ─────────────────────────┘                ▲             │ needsFix          │ revise
                                                                     ├── retry ────┘                   ▼
                                                                     └──────────────────────────── record-review
                                                      needsFix, no attempts left ─► return-result (outcome failed)
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Package mode: picks `tlf-plan.json` (kind `tlf-plan`), `study-model`, `sdtm`, and the context kinds `sdtm-define`, `sap`, `usdm`. No plan → fails (run tlf-planning first). With a `request` trigger input (a spec change from the TLF review, set by the master) it also picks the previous `analysis-spec.json`, `adam-spec.json`, `reporting-event.json`; missing ones fail. Standalone: routes to the upload. |
| `upload-inputs` | human (`statistician`) | `tlf-plan.json`, `study-model.json`, SDTM `.xpt`; optionally define.xml, SAP, USDM. JSON is classified by content. |
| `stage-inputs` | script | sha256-verifies and stages under `/workspace/analysis-specification/inputs`, including `sdtm-inventory.json` (shared `sdtminventory.py`: codes per SDTM domain). With a `request`: restores the previous specs into `specs/` and writes the request as the first `review-feedback.jsonl` line, so the agent revises them like a review round. |
| `build-specs` | **agent** | `tlf-analysis-spec` skill (carried): `analysis-spec.json`, `adam-spec.json`, `reporting-event.json` in `specs/`. Writes specs only. Runs `self_check.py` until PASS. |
| `check-specs` | script | The deterministic gate (`speclib.check_specs`), below. Fails go back to the agent in `feedback.json`, three attempts per review round. On pass publishes the specs and `specs.html`. |
| `review-specs` | human review (`statistician`) | Approve, or request changes with a comment. |
| `record-review` | script | Appends the comment to `review-feedback.jsonl` and resets the gate's attempts. |
| `return-result` | script | `outcome` `specified` — publishes the files exactly as `check-specs` checked them: `analysis-spec`, `ars`, `adam-spec`, `analysis-spec-view` (`specs.html`), plus `review-feedback-analysis-specification` — or `failed` (the agent's drafts attached, package specs unchanged). |

## The gate

- `reporting-event.json` validates against the CDISC ARS LDM JSON Schema
  (`artifacts/schemas/ars_ldm.schema.json`, minified; needs Python `jsonschema`, present in the
  image) — repeated errors are collapsed per collection — and every `methodId`, `analysisSetId`,
  `dataSubsetId`, `groupingId` and contents-list `analysisId`/`outputId` resolves.
- Every planned output (`status planned` + `final_id`) has exactly one `analysis-spec.json` entry
  with `table_id` = the full `final_id` (numbering restarts per type, so `T-14-5.01` and
  `L-14-5.01` both exist) and one ARS analysis `AN.<final_id>` and output `OUT.<final_id>`;
  nothing blocked or flagged is specified.
- Every entry has methods and an analysis-set condition, its `dataSubset.dataset` is in the ADaM
  spec, and every variable named in an analysis-variable or grouping `variable` field (split on
  `/`, `,`, spaces; free text ignored) is in that dataset or ADSL.
- The ADaM spec is what `adam-derivation` consumes: ADSL present, `AD…` dataset names, classes
  ADSL/BDS/OCCDS/TTE, upper-case ≤ 8-character variable names without repeats, literal PARAMCDs
  (`ALT/AST` is rejected; `<LBTESTCD>`-style placeholders pass), `used_by_tables` naming planned
  outputs and covering all of them, `mandatory_derivation_rules` and `data_quality_gate` present,
  and every `sdtm_source` SDTM domain delivered (when SDTM was supplied; ADaM names such as ADSL
  are skipped).

Run on the original UC3 specs, the gate finds real defects (ARS `dataSubsets` shape, a
contents-list `name`, a deaths listing L-14-5.01 without methods, MHTERM with no ADMH, a
composite PARAMCD); `tests/fixtures/specs` is that set corrected and keyed by `final_id`.

## Test

```bash
python3 tests/test_pipeline.py    # needs R with haven + jsonlite, Python jsonschema
```

Covers package mode, a change request (previous specs restored, request recorded; no previous specs → fails), seven seeded defects through three attempts to `failed`, and upload mode
with a review round. The plan comes from `../tlf-planning/tests/fixtures`.
