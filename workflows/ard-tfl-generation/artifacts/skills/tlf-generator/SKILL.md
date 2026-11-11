---
name: tlf-generator
description: "Generate the actual Tables, Listings, and Figures (TLFs) from an ARS-aligned analysis spec + ADaM data, ARD-first: compute every statistic into Analysis Results Data (ARD) with {cards}/{cardx}/emmeans, then render the ARD to the target display shape as HTML tables whose cells name their ARD rows and {ggsurvfit} (Kaplan-Meier figures), applying SAS rounding at display time. Use this skill when the user has an analysis-spec.json (from tlf-analysis-spec) plus ADaM datasets and wants to produce the numbers and the displays. Also trigger on: 'generate TLFs/tables/figures', 'produce ARD', 'analysis results data', 'cards/cardx tables', 'ANCOVA LS-means table', 'Kaplan-Meier figure', 'ADaM to tables', or 'compute the numbers for the tables'. This is Stage-3 of the Protocol->TLF pipeline and REPLACES/UPGRADES the older adam-to-tlg skill with an ARD-native numbers-then-format approach; prefer this skill over adam-to-tlg when an analysis spec exists."
---

# TLF Generator

## Purpose

Turn a **human-reviewed analysis spec** (from `tlf-analysis-spec`) plus **ADaM datasets** (from
`sdtm-to-adam`) into the two artifacts that matter: the **numbers** (ARD) and the **display**
(rendered TLF). Every displayed value is **computed from ADaM, never hand-entered** — the ARD is the
single source of truth for every cell.

This is **Step 3** of the automated TLF workflow:

```
USDM ─▶ [tlf-planner]+[tlf-plan-critic] ─▶ tlf-plan ─▶ [tlf-analysis-spec] ─▶ analysis-spec.json + adam-spec
                                                                                    │
                                                        [sdtm-to-adam] ─▶ ADaM datasets
                                                                                    │
                                              analysis-spec.json + ADaM ─▶ [tlf-generator] ─▶ ARD ─▶ rendered TLF
```

## Relationship to `adam-to-tlg` (what this replaces)

`adam-to-tlg` reads mock shells and computes-and-formats in one `gtsummary`/`gt` pass — the classic
mistake that makes a wrong cell impossible to trace. `tlf-generator` supersedes it with the
**three-artifact discipline** (§1 of `adam-to-tlf-design.md`): the recipe (analysis spec), the
**numbers** (ARD, persisted), and the **display** (rendered from the ARD). Prefer `tlf-generator`
whenever an `analysis-spec.json` exists. `adam-to-tlg` is **not deleted** — it remains the fallback
for the older mock-shell-driven path, but new work should go through this skill.

## The core rule: numbers → ARD → display, in that order

Keep the two phases strictly separate (from `references/generation-idioms.md` "Golden rules"):

1. **Compute** every statistic into a tidy **ARD** and persist it (`ard.csv` / `ard.json`).
2. **Render** the ARD to the target row/column shape (from the analysis-spec + standard CSR conventions).
3. **Never compute inside the renderer; never hand-enter a value** — every cell reads from the ARD.
4. Apply **SAS rounding at display time only** — R's `round()` is banker's (half-to-even); SAS output
   is half-away-from-zero. Round in the formatting layer, not in the stats.

## Inputs and outputs in this workflow (the program contract)

You write **R programs only**. A deterministic step runs each one in a fresh `Rscript --vanilla`
session and a second one reconciles the display with the ARD; nothing you compute in your own
session is used. Read the contract in `/artifacts/scripts/tfllib.py` (docstring) — it is enforced.

Inputs (read-only), under `/workspace/ard-tfl-generation/inputs/`:
- `analysis-spec.json` — one entry per output (`table_id`), schema in the analysis-specification workflow.
- `reporting-event.json` — the ARS ReportingEvent; your tag names the analysis `AN.<final_id>`.
- `tlf-plan.json` — titles and types (Table / Listing / Figure) by `final_id`.
- `adam/<dataset>.xpt` — the ADaM datasets (`haven::read_xpt`); `adam-columns.json` lists their columns.
- `lineage.json` (when present) — how each ADaM variable was derived.

Write `/workspace/tlf-programs/<final_id>.R`, one per output that has an analysis-spec entry, plus
an optional `setup.R` with shared helpers (`source("setup.R")`; programs run with the programs
folder as working directory). Each program:

```r
# @tlf T-14-3.01 analysis=AN.T-14-3.01 uses=ADSL.EFFFL,ADSL.TRT01P,ADQSPHQ.CHG,ADQSPHQ.BASE,ADQSPHQ.ANL01FL
adsl <- haven::read_xpt(file.path(Sys.getenv("ADAM_DIR"), "adsl.xpt"))
...                                            # Phase A: numbers -> ard (long, one row per statistic)
jsonlite::write_json(ard, file.path(Sys.getenv("ARD_DIR"), "T-14-3.01.json"), auto_unbox = TRUE, digits = NA)
...                                            # Phase B: display rendered FROM ard only
writeLines(html, file.path(Sys.getenv("TFL_DIR"), "T-14-3.01.html"))   # hand-built <table>, cells carry data-ard
```

- The ARD is a JSON array; every row has `variable`, `stat_name`, `stat` (+ `group1`, `group1_level`,
  `variable_level`, `context` where they apply). Write numbers at full precision (`digits = NA`).
- Tables and listings: an HTML `<table>` you build yourself (`gt`/`gtsummary` cannot set cell
  attributes); the first cell of each row is its label. **Every other cell that shows numbers names
  their ARD rows**: `<td data-ard="12,13">73.6 (9.94)</td>` — 0-based indices into the ARD array, one
  per number in the cell, in order. Each number must be exactly that row's `stat` rounded half away
  from zero at the shown decimals (a proportion may be shown × 100 — write `%` after it; `<0.001`
  must bound it). Listings show ADaM records: their cells need no `data-ard`. The
  reconcile step rejects a missing, miscounted or wrong index — matching some other ARD value does
  not count — so put N, n, %, CIs and p-values in the ARD first. Headers (`<th>`-only rows) are not
  checked. Look the index up from the ARD data frame you wrote, never count by hand:

  ```r
  ard_row <- function(ard, ...) {                 # 0-based row of the one ARD row matching column = value
    wanted <- list(...)
    index <- which(Reduce(`&`, Map(function(column, value) ard[[column]] == value, names(wanted), wanted)))
    stopifnot(length(index) == 1)
    index - 1
  }
  td <- function(text, rows) paste0("<td data-ard='", paste(rows, collapse = ","), "'>", text, "</td>")
  td(paste0(fmt(mean, 1), " (", fmt(sd, 2), ")"), c(ard_row(ard, group1_level = arm, stat_name = "mean"),
                                                    ard_row(ard, group1_level = arm, stat_name = "sd")))
  ```

  Write the ARD from that same data frame without reordering rows after the indices are taken.
- Figures: `<final_id>.png` (`ggplot2::ggsave`, 150-300 dpi); the curve's numbers still go to the ARD.
- `uses=` lists every ADaM `DATASET.VARIABLE` the program reads; it is the trace from each output to
  the ADaM derivation lines in the viewer.

Run `python3 /artifacts/scripts/self_check.py` (executes every program and reconciles) until it
prints PASS. If `/workspace/ard-tfl-generation/feedback.json` exists, a gate rejected your last
programs: fix exactly what it lists. If `/workspace/ard-tfl-generation/review-feedback.jsonl`
exists, its last line is the reviewer's request: change only the programs it concerns.
Then write `/output/result.json`: `{"summary": "...", "outputs": n, "notes": ["data or spec issues for the reviewer"]}`.

## Workflow

### Step 0 — Environment

Ensure packages (versions validated on this machine, from `references/generation-idioms.md`):
`cards` 0.7.1.9008, `cardx` 0.3.2.9001, `gtsummary` 2.5.0.9003, `emmeans` 2.0.3, plus `dplyr`,
`tidyr`, `survival`, `ggsurvfit`, `mmrm`, `jsonlite`. Read each TLF's analysis-spec entry
(`groupingFactor`, `analysisVariables`, the method `display` block) — the source of its row labels
and column order — plus its mock shell if one exists, before generating its script.

### Step 1 — Setup script (`00_setup.R`)

Emit the shared helpers exactly as in the idioms bible:

```r
# SAS-style rounding (round half away from zero) — DISPLAY ONLY
sas_round <- function(x, d = 0) { z <- abs(x) * 10^d; z <- floor(z + 0.5); sign(x) * z / 10^d }
fmt <- function(x, d) formatC(sas_round(x, d), format = "f", digits = d)
read_adam <- function(name) read.csv(file.path(ADAM_DIR, paste0(name, ".csv")), stringsAsFactors = FALSE)
```

**Population N always comes from ADSL** (one row per `USUBJID`), never from a BDS dataset (ADQS,
ADAE, …) which has many rows per subject and inflates N. Compute per-population N by arm once here.

---

### Phase A — ARD (the numbers)

For each TLF, one script that:

1. **Filter the analysis population.** Apply `analysisSet.condition` (e.g. `EFFFL == "Y"`) and
   `dataSubset.condition` (e.g. `PARAMCD == "ACTOT11" & AVISITN == 24 & ANL01FL == "Y"`). Set the
   treatment factor levels **and reference** from `groupingFactor.levels` (order + `isReference`).
2. **Assert N** against the population flag before computing — a data-quality gate:
   `stopifnot(!anyNA(ANL$TRTP), n_distinct(ANL$USUBJID) == nrow(ANL))`, then print `table(ANL$TRTP)`.
3. **Compute per method** using the right engine (catalog below). Descriptives via
   `cards::ard_continuous`; ANCOVA LS-means/contrasts via **`emmeans` directly** (not
   `cardx::ard_emmeans_contrast` — see warning); CMH via `cardx::ard_stats_mantelhaen_test`; KM via
   `cardx::ard_survival_survfit`; MMRM via **custom ARD**.
4. **Assemble a tidy ARD** — long format, one row per statistic:
   `group1, variable_level, context, stat_name, stat`. Flatten `ard_continuous` (its `group1_level`
   and `stat` are **list-columns holding factors** — coerce with `as.character()`/`as.numeric()`),
   bind the model rows, then `write.csv` + `jsonlite::write_json(..., auto_unbox = TRUE)`.

**Engine map** (from `adam-to-tlf-design.md` §5 and the schema catalog; ⚠️ = assemble, ❌ = custom):

| Method (spec) | Engine | Note |
|---|---|---|
| `Descriptive` | `cards::ard_continuous` / `ard_categorical` | ✅ wrap stats in `cards::continuous_summary_fns(...)` — bare string shortcut is broken in this cards build |
| `Incidence` (AE) | `cards::ard_hierarchical` / `cardx::ard_tabulate` | ✅ |
| `ShiftTable` (labs) | `cardx::ard_tabulate_shift` / `_abnormal` | ✅ |
| `Fisher` / `ChiSquare` | `cardx::ard_stats_fisher_test` / `ard_stats_chisq_test` | ✅ |
| `CMH` (CIBIC+) | `cardx::ard_stats_mantelhaen_test` | ✅ watch sparse strata — plan a `MASS::ginv` fallback |
| `ANCOVA` + LS-means | `lm(...)` + **`emmeans::emmeans` + `emmeans::contrast`** | ⚠️ assemble; explicit coef signs |
| `DoseResponse` | `lm(CHG ~ DOSE + …)`, read `summary(fit)$coefficients["DOSE","Pr(>|t|)"]` | ⚠️ dose as continuous |
| `KaplanMeier` | `cardx::ard_survival_survfit` (+ `_survfit_diff`) | ✅ figure → render with ggsurvfit |
| `LogRank` | `cardx::ard_survival_survdiff` | ✅ |
| `Cox` | `cardx::ard_regression` on `survival::coxph` | ⚠️ assemble |
| `MMRM` | `mmrm::mmrm()` + `emmeans` → **custom ARD** (`tidy_as_ard`/manual bind) | ❌ no cardx fn |

**ANCOVA / LS-means — use `emmeans` directly** (validated pattern; full code in the idioms bible):

```r
fit <- lm(CHG ~ TRTP + SITEGR1 + BASE, data = ANL)       # site group factor, baseline covariate
emm <- emmeans(fit, ~ TRTP)                              # equal ref-grid weighting = SAS LSMEANS default
ct  <- contrast(emm, method = list(                      # EXPLICIT coefs → sign = dose − reference
  "Xanomeline Low Dose - Placebo"   = c(-1, 1, 0),
  "Xanomeline High Dose - Placebo"  = c(-1, 0, 1),
  "Xanomeline High Dose - Low Dose" = c( 0,-1, 1)), infer = c(TRUE, TRUE))
```

> ⚠️ **`cardx::ard_emmeans_contrast` returned all-NULL stats in the tested build — do NOT use it.**
> Call `emmeans::emmeans` + `emmeans::contrast` and assemble the ARD yourself. Pass **explicit
> coefficient lists** (don't trust `pairwise`/`trt.vs.ctrl` default signs). Read the coef vectors
> and reference level from `groupingFactor.levels`.

> ❌ **MMRM needs custom ARD** — there is no cardx function and `mmrm` isn't a cardx dependency. Fit
> `mmrm::mmrm()`, pull LS-means/contrasts with `emmeans`, and hand-build the tidy ARD rows. Pin the
> covariance structure and DoF method (Kenward-Roger vs Satterthwaite) to the SAP or the numbers drift.

---

### Phase B — Display (the format)

Render the persisted ARD to the target row/column shape defined by the **analysis-spec** —
`groupingFactor.levels` become the columns (in order, reference first), and `analysisVariables` +
the method `display` block become the rows — following standard CSR table conventions. If a mock TLG
shell was provided for the TLF, match its exact layout (row labels and footnote markers kept verbatim).

- **Tables:** build the HTML `<table>` directly from the ARD (each numeric cell with its `data-ard`
  rows — see the program contract above). Pull values from the ARD and apply `fmt()`
  (SAS rounding) at each statistic's **display precision** from the method's `display` block
  (e.g. mean to 1 dp, SD to 2 dp, median to 1 dp, range as integers, p-values to 3 dp).
- **Column order and reference** come from `groupingFactor.levels`; **N in headers** from ADSL.
- **Figures (KM):** `ggsurvfit` — see below.
- Numbers and their `data-ard` matter more than pixel fidelity on the first build.

---

## Accuracy watch-list (from `adam-to-tlf-design.md` §6)

Ordered by how often they bite. When numbers are wrong, check these first:

1. **Populations/flags are upstream in ADaM.** LOCF/OC/windowed/completers are `ANLxxFL`;
   populations are `SAFFL/EFFFL/COMPLFL/ITTFL`. A wrong flag corrupts every N, %, and LS-mean even
   with a perfect model. If N per arm looks wrong, the fault is in ADaM, not the stats — flag it in
   `issues.md` (a denominator mismatch like `79/81/74` vs an expected `76/75/65` sinks a whole table).
   **Review the population/subset conditions hardest.**
2. **SAS rounding** — replicate half-away-from-zero via `sas_round()` in the formatter.
3. **LS-means/contrast setup** — exact model (`CHG ~ TRTP + SITEGR1 + BASE`, Type III), exact
   contrast, equal reference-grid weighting; factor vs continuous dose flips the p-value.
4. **MMRM** — covariance structure + DoF method pinned to the SAP.
5. **Factor level ordering** — set treatment order/reference explicitly or columns/contrasts invert.
6. **Sparse-stratum CMH** — R may refuse a p-value; fall back to `MASS::ginv`.
7. **Dataset provenance** — validate denominators explicitly; PHUSE Test-Data-Factory flags can
   differ from the original CDISC Pilot analysis data.

## Worked example — generating T-14-3.01

`T-14-3.01` (ADAS-Cog(11) CFB→Wk24, LOCF, ANCOVA) is the proven end-to-end template; the reference
implementation is `testing-tlf-planner/spike-T-14-3.01/generate.R` and its idioms are distilled in
`references/generation-idioms.md`. The generated script:

1. **Population/subset:** filter `ADQSADAS` to `PARAMCD == "ACTOT11" & AVISITN == 24 & ANL01FL == "Y"
   & EFFFL == "Y"` (note: `ACTOT11` is the total, not `ACTOT` the subscore), factor `TRTP` with
   Placebo as reference, `SITEGR1` as factor; assert one row per subject.
2. **Phase A / ARD:** `cards::ard_continuous(by = TRTP, variables = c(BASE, AVAL, CHG), statistic =
   everything() ~ cards::continuous_summary_fns(c("N","mean","sd","median","min","max")))` for the
   descriptives; `lm` + `emmeans` + explicit-coef `contrast` for LS-means/diffs/CIs/p-values; a
   second `lm(CHG ~ DOSE + SITEGR1 + BASE)` with `DOSE = TRT01PN` for the continuous dose-response
   p. Bind all into one tidy ARD; write `ard.csv`/`ard.json`.
3. **Phase B / display:** render the CSR's rows (Baseline / Week 24 / Change from Baseline blocks
   with n, Mean (SD), Median (Range); then Dose-Response p, pairwise p, Diff of LS Means (SE), 95%
   CI), applying `fmt()` — mean 1 dp, SD 2 dp, median 1 dp, range integers, p-values 3 dp.

The spike reproduced this table exactly once the ADaM denominators were correct — the residual error
was upstream in ADaM, not in the generator.

## How a KM figure (F-14-1) differs — `ggsurvfit`

`F-14-1` (Time to Dermatologic Event) is a **figure**, not a table, so the display path changes:

- **Phase A / ARD** is still survival stats, not descriptives: build the survival object
  (`survival::Surv(AVAL, 1 - CNSR)` on `ADTTE`, filtered to `SAFFL == "Y"`, the derm-event
  parameter) and compute with `cardx::ard_survival_survfit` (N, events, censored, median survival +
  95% CL per arm) and `cardx::ard_survival_survdiff` for the **log-rank p**. Persist to `ard.json`.
- **Phase B / display** uses **`ggsurvfit`**, not `gtsummary`: `survfit2(Surv(...) ~ TRTP)` →
  `ggsurvfit()` + `add_censor_mark()` + `add_risktable()` (number-at-risk), distinct line types per
  arm (Placebo solid, High dotted, Low dashed per convention), axis 0–200 days / 0–1 survival, log-rank
  p annotation. Export **`.png` at 300 dpi** (~10×7 in).
- **Summary block:** alongside the curve, emit the figure's **Summary Statistics** block (subjects,
  event/censored %, median survival + 95% CL) as a small markdown table, pulled from the same ARD.

## Reference files

- `references/generation-idioms.md` — the validated cards/cardx/emmeans idioms (SAS rounding,
  `ard_continuous` API note, the `ard_emmeans_contrast` breakage, ARD assembly). **Read first.**
- `../tlf-analysis-spec/references/analysis-spec-schema.md` — the input contract (method catalog,
  `groupingFactor.levels`, ANCOVA sub-objects).
- the protocol-to-tfl adam-to-tlf design note — the Steps 2–3 design (§1 three artifacts, §5 method map,
  §6 accuracy watch-list). *(repo root)*
- `../../../../testing-tlf-planner/spike-T-14-3.01/generate.R` — the proven end-to-end template. *(repo root)*
