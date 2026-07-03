# cdisc-case-3 — ARS Reporting Event + ADaM → traceable TFLs

A Mediforce workflow for the CDISC AI Innovation Challenge, **Use Case 3:
AI-Driven Tables, Figures, and Listings (TFL) Generation**. It **executes** a
machine-readable CDISC **ARS v1.0 Reporting Event** (the SAP-as-data from Case 2)
against **ADaM** datasets to produce Tables, Figures, Listings and **Analysis
Results Datasets (ARD)** with end-to-end objective→result traceability.

**Thesis:** *execute the spec, don't reconstruct it.* Standard safety outputs run
through deterministic, validated **recipes**; the AI **drafts programs** only for
the custom efficacy outputs no validated code covers; a **human reviews** the
drafted programs before packaging. Traceability is exact **by construction** —
every result cell carries the ARS analysis/operation id that produced it.

See [`../mediforce/PLAN-3.md`](../mediforce/PLAN-3.md) for the full design.

## Steps

| # | Step | executor / plugin | What it does |
|---|------|-------------------|--------------|
| 1 | Provide inputs | `human` | Upload an ARS Reporting Event JSON + ADaM (or leave empty for the bundled CDISCPILOT01 reference) |
| 2 | Stage inputs | `script` | Resolve uploaded-or-bundled → `/workspace/reporting_event.json` + `/workspace/adam/` |
| 3 | Generate TFLs | `agent` + `ars-to-tfl` skill | **AI.** Bind ARS↔ADaM; classify each output standard/custom; run recipes / draft + repair programs → ARD + rendered display |
| 4 | Review programs | `human` (`type: review`) | Approve → package; Request Changes → back to Generate with the comment |
| 5 | Package TFLs | `script` (R) | Coverage gate; consolidate `ard.csv`; write results back into the Reporting Event; build `traceability.html`; `manifest.json` |

## Two-mode execution (the design fact)

- **Standard safety outputs** (demographics, overall AE, AE by SOC/PT, vitals) →
  the deterministic **recipe library** (`container/recipes/recipes.R`), built on
  `cards`/`cardx`/`gtsummary`. The agent only supplies bindings; the executing
  code is fixed and validated. "Almost all safety outputs for free."
- **Custom efficacy outputs** (ADAS-Cog ANCOVA, time-to-event Kaplan-Meier) →
  the agent **drafts a standalone program**, runs it, repairs until it renders,
  and a human reviews it. Even here it emits the same long-skinny ARD contract.

`siera` (the ARS-native CRAN package) is deliberately **not** used — it is
pre-1.0 and its back end is not production-grade (per practitioner review). The
agent drafts analysis R directly on `cards`/`cardx` instead. See PLAN-3 §3.

## The long-skinny ARD contract

Every output — recipe-driven or agent-drafted — writes
`/workspace/ard/<outputId>.csv` with:

```
output_id, analysis_id, operation_id, group_var, group_level,
variable, variable_level, stat_name, stat_label, stat_raw, stat_fmt
```

`package.R` consolidates all of these into one `/output/ard.csv` (the reusable,
loadable results-by-row frame) and writes each value back into the matching
`Analysis.results[]` of `reporting_event_with_results.json` — spec in, completed
spec out, one CDISC artifact.

## Layout

```
container/stage_inputs.py          step 2 (resolve uploaded-or-bundled inputs)
container/recipes/recipes.R        the validated standard-output recipe library
container/recipes/example_driver.R WORKING reference driver for the agent (all 7 outputs)
container/package.R                step 5 (coverage gate + ard.csv + write-back + traceability)
plugins/cdisc-case-3/skills/ars-to-tfl/SKILL.md   step 3 skill (the AI value-add)
fixtures/reporting_event.json      bundled CDISCPILOT01 ARS (5 safety + 2 efficacy outputs)
fixtures/adam/*.csv                bundled CDISCPILOT01 ADaM
fixtures/ars_ldm.schema.json       pinned ARS v1.0 JSON schema
fixtures/curate_fixture.py         how the bundled Reporting Event was curated (provenance)
Dockerfile                         golden image + cards/cardx/gtsummary/survival/emmeans
src/cdisc-case-3.wd.json           the workflow definition
```

The bundled Reporting Event is the official CDISC ARS v1 **Common Safety
Displays** example (CDISCPILOT01), results stripped, plus two authored efficacy
outputs for the custom path — see `fixtures/curate_fixture.py`.

## Key wiring (mirrors cdisc-case-1)

- **Image** built lazily from each step's `repo`+`commit`+`dockerfile`+`repoAuth`
  (HTTPS-token clone). Skills read at run time from `externalSkillsRepo` +
  `skillsDir` — not baked into the image.
- **Downloadable artifacts** go to `/output`; `/workspace` passes data between
  steps.
- **Review step** routes `approve → package-tfl`, `revise → generate-tfl` (with
  the reviewer comment), mirroring the golden-standard-workflow review shape.

## Secrets (on the target instance)

| Secret | Used by |
| ------ | ------- |
| `GITHUB_TOKEN` | image build + skill clone (all container/agent steps) |
| `OPENROUTER_API_KEY` | the `generate-tfl` agent step |

## Runbook

```bash
cd /Users/vedha/Repo/cdisc-case-3
git init && git add -A && git commit -m "cdisc-case-3: ARS Reporting Event -> traceable TFLs"
gh repo create cdisc-case-3 --public --source=. --push
git rev-parse HEAD    # set this SHA into every commit field + externalSkillsRepo in src/cdisc-case-3.wd.json

docker build -t mediforce-agent:cdisc-case-3 .   # needs mediforce-golden-image

BASE=https://cdisc.mediforce.ai/
MEDIFORCE_API_KEY=$(cat ~/.config/mediforce/cdisc-key) \
pnpm exec mediforce workflow register --file=src/cdisc-case-3.wd.json --namespace=cdisc --base-url=$BASE

MEDIFORCE_API_KEY=$(cat ~/.config/mediforce/cdisc-key) \
pnpm exec mediforce run start --workflow="Use Case 3: AI-Driven Tables, Figures, and Listings (TFL) Generation" --namespace=cdisc --base-url=$BASE
```

Complete **Provide inputs** in the UI (leave empty for the bundled CDISCPILOT01).
Steps 2–5 run automatically; the TFLs, `ard.csv`, `traceability.html`, and
`reporting_event_with_results.json` appear as downloads on **Package TFLs**.
