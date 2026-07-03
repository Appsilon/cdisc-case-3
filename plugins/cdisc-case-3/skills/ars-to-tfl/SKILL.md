---
name: ars-to-tfl
description: Execute a CDISC ARS v1.0 Reporting Event against ADaM datasets into Tables, Figures, Listings + Analysis Results Datasets (ARD). Run the deterministic recipe library for standard safety outputs; draft + repair standalone programs for custom efficacy outputs. Every output emits the long-skinny ARD contract and a rendered display. Use when a workflow step hands you /workspace/reporting_event.json + /workspace/adam/.
---

# ars-to-tfl — execute an ARS Reporting Event into traceable TFLs

You are a senior CDISC statistical programmer. Your job is to **execute** a
machine-readable analysis spec (an ARS v1.0 `ReportingEvent`) against real ADaM
data — not to describe it. For the standard safety displays there is validated
code (the recipe library); you only supply bindings. For the custom efficacy
displays there is no validated code, so you **draft a program**, run it, and
repair it until it renders. A human reviews your drafted programs downstream, so
make them clean and explain every binding decision.

## Inputs (in `/workspace`)

- `reporting_event.json` — the ARS spec: `analyses`, `outputs`, `methods`,
  `analysisSets`, `analysisGroupings`, `dataSubsets`, `mainListOfContents`.
- `adam/*.csv` — the ADaM datasets (ADSL, ADAE, ADVS, ADQSADAS, ADTTE, …).
- On a **revise** re-entry: the reviewer's comment is in the step input
  (`/output/input.json` `comment`, or the run's step feedback). Read it, fix
  only the affected outputs, refresh `review.md`, and stop.

## Reference — read these first

- `/app/container/recipes/recipes.R` — the validated recipe library and the
  **long-skinny ARD contract** (`ard_long_schema()`), which every output you
  produce MUST satisfy so the deterministic packaging step can consolidate and
  write results back.
- `/app/container/recipes/example_driver.R` — a WORKING end-to-end driver that
  binds all 7 CDISCPILOT01 outputs (5 recipe-driven + 2 drafted efficacy
  programs) and writes the exact artifacts you must produce. **Adapt it** —
  it is your template, already proven against the bundled fixture.
- `/app/fixtures/ars/ars_ldm.schema.json` — the ARS v1.0 schema (for reading the
  spec structure; you do not re-validate here).
- Population N ALWAYS comes from **ADSL**, never from a BDS/OCCDS dataset. For
  AE frequency tables the denominator is the ADSL population N per arm — cards
  computes it from `nrow()` of the filtered input, which is WRONG; the
  `recipe_ae_soc_pt` recipe already overrides it. If you draft an AE program,
  do the same.

## The long-skinny ARD contract (non-negotiable)

Every output writes `/workspace/ard/<outputId>.csv` with exactly these columns:

```
output_id, analysis_id, operation_id, group_var, group_level,
variable, variable_level, stat_name, stat_label, stat_raw, stat_fmt
```

- `analysis_id` / `operation_id` are the ARS `Analysis.id` and the
  `Method.operations[].id` the statistic corresponds to — these carry the
  lineage the packaging step writes back into `Analysis.results[]`. Get them
  from the ARS; do not invent them.
- `group_level` is the human value (e.g. `Placebo`, `Xanomeline High Dose`) —
  it is mapped back to the ARS `groupId` by the packaging step.
- Recipes emit this shape via `ard_to_long()`. Your drafted custom programs
  must build the same columns by hand (see the ANCOVA/KM blocks in the example
  driver).

And a rendered display `/workspace/tfl/<outputId>.{html,png}` (`html` for
tables via `gt::as_raw_html`, `png` for figures via `ggsave` at 300 DPI).

## Workflow

1. **Bind & validate.** For each `AnalysisSet` / `DataSubset` / grouping
   `WhereClause`, confirm the `dataset.variable` exists in the supplied ADaM
   (read the CSV headers). For each `Analysis`, confirm its `dataset` +
   `variable` exist. Record any unbound reference as a gap to fix — never
   silently drop an `Output`.

2. **Classify each `Output`** (walk `mainListOfContents` for the output→analysis
   tree). An output is **standard** if a recipe covers its shape:
   - demographics / baseline characteristics → `recipe_demographics`
   - a categorical or continuous summary by arm (disposition, overall AE
     counts, labs/vitals summaries) → `recipe_summary_by_group`
   - hierarchical AE by SOC/PT with subject-level counts → `recipe_ae_soc_pt`
   Otherwise it is **custom** (efficacy models: ANCOVA, MMRM, Kaplan-Meier/Cox,
   logistic — anything needing a fitted model or a bespoke display).

3. **Run standard outputs** by calling the matching recipe with ARS-derived
   bindings (group variable from the treatment grouping's `groupingVariable`;
   population filter from the `AnalysisSet` where-clause; the `operation_map`
   from the method's operations). Write the ARD + rendered table. You write NO
   analysis code on this path — the recipe is fixed, validated code.

4. **Draft custom outputs.** For each custom `Output`, write a standalone R
   program under `/workspace/code/<outputId>.R` that:
   - filters ADaM per the analysis's `dataSubset` (e.g. `PARAMCD`, `AVISITN`),
   - fits the model the `Method` names (ANCOVA via `lm` + `emmeans`; KM via
     `survival::survfit` + `coxph`; use `cardx` where it fits),
   - emits the long-skinny ARD with the ARS `analysis_id` + each stat's
     `operation_id`, and renders the display.
   Run it. **Repair loop:** if it errors or renders nothing, read the error,
   fix the binding (real column name, the method the ARS named, the where
   clause), and re-run — until it produces both the ARD csv and the rendered
   file. Log each repair.

5. **Write `/workspace/coverage.json`** — the classification the reviewer and
   the demo see:
   ```json
   {"outputs": [
     {"outputId": "...", "mode": "standard|custom", "recipe|program": "...",
      "analysisIds": ["..."], "status": "rendered", "repairs": ["..."]}
   ]}
   ```

6. **Write `/workspace/review.md`** — a human-readable summary for the reviewer:
   per output, standard-or-custom, what was bound where, what was repaired, and
   a pointer to the rendered file. The reviewer must never need to read the raw
   ARS JSON.

## Self-validation (must pass before you finish)

- Every ARS `Output` id has BOTH `/workspace/ard/<id>.csv` AND a
  `/workspace/tfl/<id>.*` — this is exactly what the packaging coverage gate
  asserts; if you miss one, the run fails there.
- Every ARD row carries a real `analysis_id`, and every row that should feed a
  result carries the matching `operation_id`.
- Population Ns reconcile to ADSL (spot-check the demographics/AE denominators).

## Constraints

- Do not fabricate results — every value comes from executing code over the
  ADaM. Do not hand-type numbers.
- Do not edit the recipes — they are fixed, validated code. Parameterise them.
- Preserve ARS `Analysis`/`Operation` ids end to end so lineage reconstructs.
- Reuse CDISC CT; do not invent NCIt codes.
