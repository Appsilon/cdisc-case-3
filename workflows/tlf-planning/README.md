# tlf-planning

Plan the exhaustive, traceable list of Tables, Listings and Figures a study
needs, from its USDM study definition. Part of the modular protocol-to-TFL set:
runs on its own (upload the USDM) or inside a parent workflow (study package in
the trigger).

```
resolve-inputs ─needsUpload─► upload-inputs ─► stage-inputs ─► plan-tlfs ─► check-plan ─► audit-plan ─► review-plan ─approve─► return-result ─► done
       └──────── package ─────────────────────────┘               ▲              │ needsFix                  │ revise
                                                                   ├── retry ─────┘                           ▼
                                                                   └─────────────────────────────────── record-review
                                                    needsFix, no attempts left ─► return-result (outcome failed)
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Package mode: picks `usdm` and the context kinds `sap`, `protocol`, `shells`, `sdtm`. No USDM → fails (points at protocol-digitization when a protocol is there). Standalone: routes to the upload. |
| `upload-inputs` | human (`statistician`) | USDM JSON; optional SAP/protocol (PDF/text/docx; `sap` in the name = SAP, `shell` = shells, else protocol) and SDTM `.xpt`/`.sas7bdat`. |
| `stage-inputs` | script | sha256-verifies and stages under `/workspace/tlf-planning/inputs`: `usdm.json`, `sap/`, `protocol/`, `shells/`, and `sdtm-inventory.json` — per SDTM domain the records, variables and distinct `--CAT/--SCAT/--TESTCD/--TEST/--PARMCD/--DECOD` values (R `haven`), so feasibility is judged on what the data holds, not on file names. |
| `plan-tlfs` | **agent** | `tlf-planner` skill (carried in `artifacts/skills/`): study model, ICH E3 scaffolding, efficacy/safety/special-domain candidates, variants, feasibility, numbering. Writes `plan/{study-model.json, tlf-plan.json, tlf-index.md}`, runs `self_check.py` until PASS. |
| `check-plan` | script | The deterministic gate (`planlib.check_plan`). Fails go back to the agent in `feedback.json`, three attempts per review round. On pass publishes the plan files and `tlf-plan.html`. |
| `audit-plan` | **agent** | `tlf-plan-critic` skill in a fresh context, reads only the plan, study model and gate result: coverage matrix, completeness heuristics, clarification items, verdict → `audit/coverage-report.md`. Never edits the plan. |
| `review-plan` | human review (`statistician`) | Approve, or request changes with a comment. |
| `record-review` | script | Appends the comment to `review-feedback.jsonl` (the planner reads the last line; skill learning reads all) and resets the gate's attempts. |
| `return-result` | script | `outcome` `planned` (publishes `study-model`, `tlf-plan` ×3 — json, md, html — `coverage-report`, `review-feedback`) or `failed` (the planner's files attached, package plan unchanged). |

## The AI / deterministic boundary

The planner and the critic are AI and write judgement: what to plan, what is
missing. The gate is a script and decides what can be decided for certain:

- both files parse; `study-model.json` has `objectives[]` and `endpoints[]`;
- every candidate follows `references/tlf-candidate-schema.md` (type, category,
  status, priority enums; a `status_reason` on every non-planned output);
- every candidate traces to an objective, an endpoint or a regulatory rule, and
  every traced id exists in the study model (no orphans, no dangling ids);
- `candidate_id`s and planned `final_id`s are unique; `final_id` matches the
  type (`T-14-…`, `L-14-…`, `F-14-…`); flagged outputs stay unnumbered;
- every resolved endpoint is traced by a candidate — planned, or blocked with a
  reason (the result lists `blockedEndpoints`: resolved endpoints with no
  producible output, e.g. the instrument is absent from the delivered SDTM);
- `tlf-index.md` lists every planned output.

## Test

```bash
python3 tests/test_pipeline.py    # needs R with haven + jsonlite (the SDTM inventory)
```

The planner stand-in is the CDISCPILOT01 plan from the original UC3 run
(`tests/fixtures/plan`, 28 tables / 1 listing / 1 figure, 20 flagged). Covers
package mode, a broken plan through three gate attempts to `failed`, and upload
mode with a review round.
