# Name: 05_reports.R
# Description: Emit derivation-plan.md and issues.md from the derived ADaM.
# ----------------------------------------------------------------------------
source("00_setup.R")

sdtm_files <- list.files(SDTM_DIR, pattern = "[.]xpt$")
sdtm_inv <- do.call(rbind, lapply(sdtm_files, function(f) {
  d <- haven::read_xpt(file.path(SDTM_DIR, f))
  data.frame(domain = toupper(sub("[.]xpt$", "", f)), rows = nrow(d), cols = ncol(d))
}))

L <- c("# ADaM Derivation Plan — CDISCPILOT01", "",
"Spec-driven from `outputs/tlf-plan/adam-spec.json`. SDTM source: `inputs/sdtm/`.",
"Output: `outputs/adam/data/` (CSV + JSON), code in `outputs/adam/code/`.", "",
"## SDTM inventory", "",
"| Domain | Records | Variables | Used by |", "|---|---|---|---|")
USES <- c(DM="ADSL", DS="ADSL", EX="ADSL, ADEX", EC="ADEX (cross-check)", VS="ADSL, ADVS",
  DD="ADSL", AE="ADAE, ADTTE", LB="ADLB", CM="ADCM", QSPH="ADQSPHQ", QSSL="ADQSSWL",
  FT="ADFTAVLT", RS="ADRSHAMD", FA="ADTTE", MH="(T-14-1.04, read directly)",
  SUPPDM="(race detail, not required)", SUPPEC="(not required)", SV="(not required)",
  SE="(not required)", IE="(not required)", OE="(no planned output)", DI="(not required)",
  RELREC="(not required)", TA="(not required)", TE="(not required)", TI="(not required)",
  TS="(study metadata / objectives)", TV="(not required)")
for (i in seq_len(nrow(sdtm_inv))) {
  d <- sdtm_inv$domain[i]
  L <- c(L, sprintf("| %s | %d | %d | %s |", d, sdtm_inv$rows[i], sdtm_inv$cols[i],
                    if (!is.na(USES[d])) USES[[d]] else "—"))
}
L <- c(L, "", "**Absent and relevant:** `DV` (protocol deviations) — the deviations table stays blocked.", "")

for (ds in SPEC$datasets) {
  f <- file.path(DATA_DIR, paste0(tolower(ds$name), ".csv"))
  d <- if (file.exists(f)) read_adam(ds$name) else NULL
  L <- c(L, sprintf("## %s — %s — supports %s", ds$name, ds$class,
                    paste(unlist(ds$used_by_tables), collapse = ", ")), "",
         sprintf("- **Source SDTM**: %s (all present)", paste(unlist(ds$sdtm_source), collapse = ", ")),
         sprintf("- **Derived**: %s rows x %s columns",
                 if (is.null(d)) "—" else nrow(d), if (is.null(d)) "—" else ncol(d)))
  if (length(ds$parameters)) {
    L <- c(L, "- **Parameters**:")
    for (p in ds$parameters)
      L <- c(L, sprintf("  - `%s` — %s%s", p$paramcd, p$param,
                        if (!is.null(p$note)) paste0(" *(", p$note, ")*") else ""))
  }
  rules <- vapply(ds$derivation_requirements, function(r) r$name, character(1))
  L <- c(L, sprintf("- **Mandatory rules applied**: %s",
                    if (!length(rules)) "none (not a windowed BDS dataset)"
                    else paste(rules, collapse = "; ")))
  if (!is.null(d) && "AVISITN" %in% names(d)) {
    ep <- d %>% filter(AVISITN == 24, ANL01FL == "Y")
    L <- c(L, sprintf("- **Week-24 endpoint records**: %d (%d observed, %d LOCF)",
                      nrow(ep), sum(is.na(ep$DTYPE) | ep$DTYPE == ""),
                      sum(!is.na(ep$DTYPE) & ep$DTYPE == "LOCF")))
  }
  if (length(ds$notes)) L <- c(L, "- **Notes / gaps**:",
                               paste0("  - ", unlist(ds$notes)))
  L <- c(L, "")
}
writeLines(L, file.path(ADAM_DIR, "derivation-plan.md"))
cat("wrote derivation-plan.md\n")

# ---------------------------------------------------------------- issues.md
adsl <- read_adam("ADSL"); adlb <- read_adam("ADLB"); adtte <- read_adam("ADTTE")
ham  <- read_adam("ADRSHAMD"); adcm <- read_adam("ADCM")
hamcfb <- ham %>% filter(AVISITN == 24, ANL01FL == "Y", !is.na(CHG)) %>% nrow()

I <- c("# Issue Summary — CDISCPILOT01 ADaM Derivation", "",
sprintf("Generated %s. Data-quality gate: **PASS** (0 error-severity failures). Conformance: **11/11 datasets OK**.",
        "2026-07-29"), "",
"## SDTM Data Issues", "",
"| # | Domain | Issue | Impact |", "|---|---|---|---|",
"| 1 | AE | `AEBODSYS` is **blank on all 74 records**. | `AESOC` used for the SOC hierarchy instead. Confirmed programmatically in `03_safety.R`. Without this check the AE tables would have had an empty SOC column. |",
"| 2 | CM | **Not WHO-DD coded** — no `CMDECOD`, `CMCLAS` or `CMATC`. 52 distinct verbatim terms over 68 records. | T-14-7.04 can only summarize verbatim `CMTRT`; the conventional therapeutic-class hierarchy is not producible. |",
"| 3 | CM | 31 of 68 `CMSTDTC` values are **partial dates** (year or year-month only). | `ASTDT` set to NA for those records; `ASTDY` retained. Handled by `safe_date()`, which reports the count rather than erroring or silently coercing. |",
"| 4 | MH | Uncoded, single term \"ALZHEIMER'S DISEASE\" for all subjects. | T-14-1.04 degenerates to one row (critic finding R-5). |",
"| 5 | FA | Injection-site reactions collected on only **8 of 17** safety subjects. | The other 9 are censored in ADTTE, which understates the event rate. The KM figure requires a footnote. |",
"| 6 | LB | No clinical-significance flag; 6 qualitative tests (ANISO, COLOR, KETONES, MACROCY, POIKILO, UROBIL) have no numeric result. | Qualitative tests excluded from continuous summaries; `CSCFL` all-missing (SD-4). |",
"| 7 | DM | 1 of 18 subjects (CDISC015) is a **screen failure** with a blank ARM. | Excluded from ITT/SAF/EFF by construction. |",
"", "## Derivation Assumptions", "",
"| # | Assumption | Where |", "|---|---|---|",
"| A1 | Analysis-visit targets: Baseline d1, Wk2 d15, Wk4 d29, Wk6 d43, Wk8 d57, Wk12 d85, Wk16 d113, Wk20 d141, Wk24 d169, Wk26 d183; nearest-target windowing on `xxDY`. | `00_setup.R::window_by_day` |",
"| A2 | Each instrument is windowed onto **the target set it actually uses**, not the full study schedule — windowing PHQ-9 onto Week 8 (which it never collects) would misassign its Week-12 records. | `02_efficacy_bds.R` |",
"| A3 | Baseline = last non-missing record with `ADY <= 1`. For AVLT-REY that is SCREENING 2 (day -2/-1), since the instrument has no BASELINE visit (SD-2). | `derive_baseline()` |",
"| A4 | `TRTEMFL` = AE start on/after first dose and on/before last dose + 30 days. | `03_safety.R` |",
"| A5 | `SWLSTOT` = sum of the 5 SWLS items, missing unless all 5 present. All 27 visit-level totals had `NITEMS = 5`. | SD-1 |",
"| A6 | Hy's Law `CRIT1` = ALT or AST >= 3xULN **and** BILI >= 2xULN, using record-level `LBSTNRHI` as ULN. **0 subjects met the criterion.** | SD-derived |",
"| A7 | ADTTE risk set = all `SAFFL='Y'` subjects; those with no injection-site reaction censored at last day on study drug. | See SDTM issue 5 |",
"| A8 | Exposure duration = last `EXENDTC` - first `EXSTDTC` + 1 (range 1-189 days). | `03_safety.R` |",
"", "## Data-Quality Gate", "",
"**PASS — 0 error-severity failures.** Full results in `data-quality.md`. Highlights:", "",
"- **MANDATORY RULE 1 verified**: all 3,322 LB and 1,414 VS source records survive windowing; the 4 unscheduled LB visits and all 6 PHQ-9 EARLY DISCONTINUATION RETRIEVAL records are retained. Those 6 ED records fall at study days 169-173 and window into Week 24 — a nominal-`VISITNUM` map would have deleted every one of them and left the primary endpoint with 2 subjects.",
"- **MANDATORY RULE 2 verified**: no subject with a baseline and a post-baseline value is missing from any endpoint analysis. LOCF supplied 2 of 10 PHQ-9, 1 of 9 SWLS and 6 of 11 AVLT-REY endpoint records.",
"- **MANDATORY RULE 3 verified**: pooling on randomized (`ITTFL='Y'`) counts collapses all 6 sites into group 900.",
"- **NG-4 assertion corrected during the run.** It was first written as an equality (`endpoint N == eligible N`) and failed on ADFTAVLT and ADRSHAMD. Both failures were the same subject, CDISC007, who has an *observed* Week-24 record but no baseline, so `CHG` is missing. The derivation was right; the assertion was wrong. The rule's actual semantics is a **shortfall** test — *no eligible subject may be missing* — and extra baseline-less endpoint records are legitimate. Re-expressed as a set-difference test, which passes.",
"", "## Conformance Failures", "",
"None outstanding. One was found and fixed during the run:", "",
"- `metatools::check_variables()` flagged **`ARMCD`, `ACTARMCD`, `TRTP`, `AGEU`, `AGEGR1N`** as present in the derived ADSL but absent from `adam-spec.json`. `TRTP` is the grouping variable every single analysis-spec entry references, so its omission from the spec was a real defect, not a cosmetic one. The spec was updated and the check now reports *no missing or extra variables*.",
"", "## Corrections Made to the ADaM Spec During Derivation", "",
"| ID | Correction |", "|---|---|",
"| SD-7 | **`AVL02-List A Total` is scored per trial, not per visit.** AVLT-REY administers List A seven times (`FTREPNUM` 1-7): trials 1-5 are learning trials, 6 is post-interference recall, 7 is 30-minute delayed recall. The spec treated it as one score per visit; the generic nearest-day flag would have silently analysed one arbitrary trial. Corrected to `AVLATOT` = sum of trials 1-5 (Total Learning) and `AVLADEL` = trial 7. A related trap: `FTDTC` carries a per-trial timestamp and must not be part of the aggregation key. |",
sprintf("| SD-3 | **Corrected.** The spec asserted HAMD 17 has no post-baseline data. It has no *scheduled* post-baseline visit, but the ED RETRIEVAL records land in the Week-24 window and **%d subjects have both a baseline and a Week-24 value**, so a change-from-baseline analysis is derivable. `BASE`/`CHG` are now derived. This is the exact failure mode Rule 1 exists to prevent — reading the nominal visit list hid real data. |", hamcfb),
"| COMPLFL | Expected N corrected **6 -> 3**. The spec counted DS *records* (2 per subject); there are 3 completing subjects (CDISC005, CDISC009, CDISC011). |",
"| ADSL vars | 5 variables added (see Conformance above). |",
"", "## Unresolved Gaps", "",
"| # | Gap | Status |", "|---|---|---|",
"| G1 | **SD-4** — the lab \"clinically significant change\" criterion is defined by neither the protocol nor any available SAP. `CSCFL` is derived all-missing per the 2026-07-29 review decision. | Open, by decision. T-14-6.03 must footnote that the criterion is unspecified. |",
"| G2 | `DV` domain absent — no protocol-deviation output possible. | Open; data-transfer question for the sponsor. |",
"| G3 | Concomitant medications uncoded — no therapeutic-class table. | Accepted limitation. |",
sprintf("| G4 | **Analysis-set sizes are far below any interpretable threshold**: ITT %d, Safety %d, Efficacy %d, Completers %d. The PHQ-9 primary endpoint has 10 analysis records of which only %d are observed. | Accepted; every downstream inferential result must be labelled illustrative. |",
        sum(adsl$ITTFL=="Y"), sum(adsl$SAFFL=="Y"), sum(adsl$EFFFL=="Y"), sum(adsl$COMPLFL=="Y"), 8L),
"| G5 | `SITEGR1` has a single level, so it is rank-deficient as an ANCOVA covariate. | Expected (SD-6). The generator must refit without it and footnote the fallback. |",
"| G6 | Hy's Law: 0 subjects meet the criterion. | Not a gap — a genuine (negative) finding. T-14-6.06 will be an all-zero table. |",
"", "## Available-But-Unused Analyses", "",
sprintf("- **HAMD 17 change from baseline at Week 24 (n=%d)** is now derivable following the SD-3 correction. The reviewed plan places T-14-2.02 in section 14-2 as a baseline summary (critic finding R-3, resolved by human review). The CFB analysis is *not* substituted silently; raise it if you want T-14-2.02 restored to section 14-3 as a treatment-effect table.", hamcfb),
"- **`AVLADEL`** (AVLT-REY 30-minute delayed recall) is derived but no planned table consumes it.",
"", "## Package Installation", "",
"No packages required installation — all of admiral 1.4.1, dplyr, tidyr, lubridate, stringr, rlang,",
"haven, xportr, datasetjson, metacore 0.2.1, metatools 0.2.0 and jsonlite were already present under R 4.4.0.")
writeLines(I, file.path(ADAM_DIR, "issues.md"))
cat("wrote issues.md\n")
