# plan-tlfs

Plan the exhaustive, traceable list of Tables, Listings and Figures a study
needs, from its USDM study definition. Part of the modular protocol-to-TFL set:
runs on its own (upload the USDM) or inside a parent workflow (study package in
the trigger).

```
resolve-inputs ─needsUpload─► upload-inputs ─► stage-inputs ─► check-study ─► plan-tlfs ─► check-plan ─► audit-plan ─► review-plan ─approve─► return-result ─► done
       └──────── package ─────────────────────────┘                   │             ▲              │ needsFix                  │ revise
                                                                       │             ├── retry ─────┘                           ▼
                                                                       │             └─────────────────────────────────── record-review
                                                    failed ─► return-result (outcome data-mismatch)
                                    check-plan: dataBlocked ─► return-result (outcome data-mismatch)
                                    check-plan: needsFix, no attempts left ─► return-result (outcome failed)
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Package mode: picks `usdm` and the context kinds `sap`, `protocol`, `shells`, `sdtm`. No USDM → fails (points at digitize-protocol when a protocol is there). Standalone: routes to the upload. |
| `upload-inputs` | human (`statistician`) | USDM JSON; optional SAP/protocol (PDF/text/docx; `sap` in the name = SAP, `shell` = shells, else protocol) SDTM `.xpt`/`.sas7bdat` and the SDTM `define.xml` (kind `sdtm-define`, carried on in the package for CORE). |
| `stage-inputs` | script | sha256-verifies and stages under `/workspace/plan-tlfs/inputs`: `usdm.json`, `sap/`, `protocol/`, `shells/`, and `sdtm-inventory.json` — per SDTM domain the records, variables and distinct `--CAT/--SCAT/--TESTCD/--TEST/--PARMCD/--DECOD` values (R `haven`), so feasibility is judged on what the data holds, not on file names. |
| `check-study` | script | The data check (`studycheck.py`): is the delivered SDTM the study the USDM describes? **Fails** (run stops, outcome `data-mismatch`) when DM has a different number of arms (randomised subjects; `shared/arms.py`) than the USDM, when the randomised count is outside 50–150 % of `plannedEnrollmentNumber`, or when no randomised subject has an EX record; **warns** when DM arm names / codes differ from the USDM arm names / labels / descriptions (parentheses and punctuation ignored — a digitized USDM may name arms differently), on TA arms, TS `PLANSUB` / `TITLE` / `TPHASE`. Placebo subjects count as exposed with `EXDOSE = 0`. No SDTM at all → one warning (planning before data exists). Writes `study-check.html` / `.json`. CORE checks conformance, not this: an 18-subject set of another study passes CORE. |
| `plan-tlfs` | **agent** | `tlf-planner` skill (carried in `artifacts/skills/`): study model, ICH E3 scaffolding, efficacy/safety/special-domain candidates, variants, feasibility, numbering. Writes `plan/{study-model.json, tlf-plan.json, tlf-index.md}`, runs `self_check.py` until PASS. |
| `check-plan` | script | The deterministic gate (`planlib.check_plan`). Fails go back to the agent in `feedback.json`, three attempts per review round. A USDM objective whose every primary endpoint has only blocked outputs is not sent back (`dataBlocked` → outcome `data-mismatch`: the planner cannot add data). On pass publishes the plan files and `tlf-plan.html` (with the data checks). |
| `audit-plan` | **agent** | `tlf-plan-critic` skill in a fresh context, reads only the plan, study model and gate result: coverage matrix, completeness heuristics, clarification items, verdict → `audit/coverage-report.md`. Never edits the plan. |
| `review-plan` | human review (`statistician`) | Approve, or request changes with a comment. |
| `record-review` | script | Appends the comment to `review-feedback.jsonl` (the planner reads the last line; skill learning reads all) and resets the gate's attempts. |
| `return-result` | script | `outcome` `planned` — publishes the files exactly as `check-plan` checked them: `study-model`, `tlf-plan` (`tlf-plan.json` only), `tlf-plan-view` (`tlf-index.md`, `tlf-plan.html`, `study-check.html` / `.json`), plus `coverage-report` and `review-feedback-plan-tlfs` — `data-mismatch` (the data-check page, and the plan drafts when a primary endpoint was blocked; package plan unchanged) — or `failed` (the planner's drafts attached, package plan unchanged). |

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
- every primary endpoint of the USDM is in the study model, not marked unresolved
  when the USDM states it, and no objective has all its primary endpoints left with only `blocked` outputs (else `dataBlocked`; one blocked primary endpoint of an objective still answered by another — e.g. ECG when the SDTM has no EG but AE/LB/VS are there — is flagged on the page and in the summary for the statistician; `needs-clarification` goes to the statistician);
- `tlf-index.md` lists every planned output (matched as a whole id, so `T-14-1` is not found inside `T-14-1.01`).

## Test

```bash
python3 tests/test_pipeline.py    # needs R with haven + jsonlite (the SDTM inventory)
```

The planner stand-in is the CDISCPILOT01 plan from the original UC3 run
(`tests/fixtures/plan`, 28 tables / 1 listing / 1 figure, 20 flagged; made on
data without ADAS-Cog / CIBIC+, so the tests plan one output per primary
efficacy endpoint where they need a passing plan). `tests/fixtures/pilot` = the
CDISCPILOT01 USDM trimmed to what the data check reads + its real DM / EX / TS /
TA; `tests/fixtures/synthetic` = DM / TS / TA of the 18-subject "Zanomaline" set
that fed every run before 2026-11-13. Covers package mode, a broken plan
through three gate attempts to `failed`, upload mode with a review round, the
wrong study's SDTM → `data-mismatch`, and both primary efficacy endpoints left blocked →
`data-mismatch`.
