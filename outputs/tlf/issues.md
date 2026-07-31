# TLF Generation — Issues & Data-Provenance Flags

Displays attempted: **30**. ARDs written: **30**. Displays rendered: **30**. Hard errors: **0**.

## Standing caveat

> This study randomized **17 subjects** (Placebo 5 / Zanomaline Low 5 / Zanomaline High 7); the
> efficacy set is 13 and the completers set is 3. Every LS-mean, contrast, CMH statistic and
> log-rank p-value produced here is **illustrative of the pipeline, not evidence about the drug**.
> Where a statistic was not estimable it is reported as `-`; no value has been substituted,
> approximated or fabricated to fill a cell.

## Per-display messages

| ID | Severity | Message |
|---|---|---|
| T-14-3.01 | INFO | analysis n=10 (observed 8, LOCF-imputed 2) |
| T-14-3.01 | WARN | SITEGR1 has a single level (all sites pooled to 900 by MANDATORY RULE 3) and is rank-deficient; the model was refitted as CHG ~ TRTP + BASE. Recorded on the display. |
| T-14-3.02 | INFO | analysis n=9 (observed 8, LOCF-imputed 1) |
| T-14-3.02 | WARN | SITEGR1 has a single level (all sites pooled to 900 by MANDATORY RULE 3) and is rank-deficient; the model was refitted as CHG ~ TRTP + BASE. Recorded on the display. |
| T-14-3.03 | INFO | analysis n=10 (observed 4, LOCF-imputed 6) |
| T-14-3.03 | WARN | SITEGR1 has a single level (all sites pooled to 900 by MANDATORY RULE 3) and is rank-deficient; the model was refitted as CHG ~ TRTP + BASE. Recorded on the display. |
| T-14-3.04 | INFO | observed-cases records: 16 across 10 subjects and 4 visits |
| T-14-3.04 | WARN | MMRM rung 'unstructured, treatment-by-visit interaction' did not converge; falling back |
| T-14-3.04 | WARN | MMRM rung 'Toeplitz, treatment-by-visit interaction' did not converge; falling back |
| T-14-3.04 | WARN | MMRM rung 'compound symmetry, treatment-by-visit interaction' converged but is numerically DEGENERATE (max LS-mean SE = 8.24e+06 vs response SD 2.14); rejected, falling back |
| T-14-3.04 | WARN | MMRM rung 'compound symmetry, interaction without BASE-by-visit' did not converge; falling back |
| T-14-3.04 | INFO | MMRM converged: compound symmetry, ADDITIVE (no treatment-by-visit interaction) (Kenward-Roger DoF); mean model CHG ~ TRTP + AVISIT + BASE |
| T-14-3.04 | WARN | MMRM fell all the way back to an ADDITIVE mean model with NO treatment-by-visit interaction. The treatment effect is therefore constrained to be identical at every visit and the per-visit contrasts WILL be identical. This is a model limitation forced by the sample size, not a finding. Stated explicitly on the display. |
| L-14-5.01 | INFO | listing: 3 row(s) |
| T-14-6.03 | INFO | CSCFL is all-missing (SD-4: criterion unspecified) — shell emitted with an explicit footnote, no invented threshold |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Baseline' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 12' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 16' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 2' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 20' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 24' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 26' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 4' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 6' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.04 | WARN | CMH p-value not estimable for stratum 'Week 8' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.05 | WARN | CMH p-value not estimable for stratum 'Overall' — sparse strata (17 subjects). Reported as NA, not fabricated. |
| T-14-6.06 | INFO | 0 subjects meet the Hy's Law criterion — a genuine negative finding, not a derivation gap |
| F-14-1 | INFO | 17 subjects, 8 events, 9 censored |

## Data-provenance flags carried onto the displays

| Display | Flag |
|---|---|
| T-14-3.01 | Analysis values are largely **LOCF-imputed** — the table face carries an explicit `n observed / n LOCF-imputed` row (critic finding R-2). |
| T-14-3.02 | Same LOCF dependency as T-14-3.01. |
| T-14-3.01/.02/.03 | **`SITEGR1` dropped from the ANCOVA model.** MANDATORY RULE 3 pooled all 6 sites into group 900 on randomized counts, leaving a single-level, rank-deficient factor. Each display footnotes the refit. |
| T-14-3.04 | MMRM covariance structure is recorded on the display; if the specified unstructured form did not converge, the fallback used is named and the non-convergence is stated rather than the table being dropped. |
| T-14-6.03 | **Cannot be populated.** The clinically-significant-change criterion is undefined by protocol and SAP (SD-4); `CSCFL` is all-missing by review decision. The display states this instead of inventing a threshold. |
| T-14-6.04/.05 | **CMH is frequently non-estimable** at 17 subjects; non-estimable p-values render as `-` with a footnote. |
| T-14-6.06 | **0 subjects meet Hy's Law.** A genuine negative finding. The display also shows the maximum observed multiple of ULN per analyte so the reader can see the distance from threshold. |
| T-14-7.04 | Concomitant medications are **not WHO-DD coded**; summarized by verbatim term under a placeholder class (critic finding R-6). |
| T-14-1.04 | Medical history is **uncoded**, single term — a one-row table (critic finding R-5). |
| F-14-1 | Injection-site reactions were collected on only **8 of 17** safety subjects; the other 9 are censored, which understates the event rate. |
| T-14-5.01..06 | **`AESOC` used, not `AEBODSYS`** — `AEBODSYS` is blank on all 74 AE records. |
| T-14-7.01/.02 | Blood pressure and pulse are reported **separately by position** (standing/supine) per USDM endpoint END4. |

## Method-engine notes

- ANCOVA LS-means and contrasts use **`emmeans::emmeans` + `emmeans::contrast` directly** with explicit coefficient lists (sign reads dose − comparator). `cardx::ard_emmeans_contrast` was not used: it returns all-NULL stats in the tested build.
- The dose-response test refits with the numeric dose `TRT01PN` as a **continuous** covariate and reads its coefficient p-value.
- MMRM has no cardx function; the ARD is hand-assembled from `mmrm::mmrm` + `emmeans`, with a documented covariance fallback ladder (unstructured → Toeplitz → compound symmetry → descriptive-only).
- Population N always comes from **ADSL** (one row per subject), never from a BDS dataset.
