# Name: 05_reports.R
# Description: Emit outputs/tlf/tlf-index.md and outputs/tlf/issues.md.
# ----------------------------------------------------------------------------
ST <- readRDS(file.path(TLF_DIR, ".status.rds"))
SECN <- c("1" = "14-1 — Subject Disposition / Populations",
          "2" = "14-2 — Demographics & Baseline Characteristics",
          "3" = "14-3 — Efficacy Analyses", "4" = "14-4 — Drug Exposure",
          "5" = "14-5 — Adverse Events", "6" = "14-6 — Laboratory Data",
          "7" = "14-7 — Vital Signs, Weight, Concomitant Medications")
secof <- function(id) if (startsWith(id, "F-")) "F" else strsplit(id, "[-.]")[[1]][3]
titleof <- function(id) {
  k <- if (startsWith(id, "T-")) paste0("AN-", sub("^T-", "", id)) else paste0("AN-", id)
  s <- SPECS[[k]]; if (is.null(s)) id else s$title
}

L <- c("# TLF Index — CDISCPILOT01", "",
sprintf("**%d displays generated** — %d ARDs, %d rendered displays, %d figure(s). Errors: %d.",
        nrow(ST), sum(ST$ard), sum(ST$display), sum(ST$png), sum(nzchar(ST$error))), "",
"ARD-first: every statistic is computed into `<id>/ard.csv` (+ `ard.json`) and the display is",
"rendered from that ARD. No value is hand-entered. SAS rounding (half away from zero) is applied",
"at display time only. The generating script for each display is copied to `<id>/generate.R`.", "",
"> **N-GATE WARNING.** 17 randomized subjects (Placebo 5 / Zanomaline Low 5 / Zanomaline High 7).",
"> Every inferential statistic below is illustrative and must not be interpreted.", "")
for (s in c("1","2","3","4","5","6","7","F")) {
  ids <- ST$id[vapply(ST$id, secof, character(1)) == s]
  if (!length(ids)) next
  L <- c(L, "", paste0("## ", if (s == "F") "Figures" else SECN[[s]]), "",
         "| ID | Title | ARD | Display | Artefacts |", "|---|---|---|---|---|")
  for (i in ids) {
    r <- ST[ST$id == i, ]
    art <- c("ard.csv", "ard.json", paste0(i, ".generated.md"), "generate.R")
    if (r$png) art <- c(art, paste0(i, ".png"))
    L <- c(L, sprintf("| [%s](%s/%s.generated.md) | %s | %s | %s | `%s` |", i, i, i, titleof(i),
                      if (r$ard) "✅" else "—", if (r$display) "✅" else "—", paste(art, collapse = "`, `")))
  }
}
writeLines(L, file.path(TLF_DIR, "tlf-index.md"))
cat("wrote tlf-index.md\n")

# ---------------------------------------------------------------- issues.md
IS <- if (length(ISSUES$rows)) do.call(rbind, ISSUES$rows) else
  data.frame(id = character(), severity = character(), msg = character())
I <- c("# TLF Generation — Issues & Data-Provenance Flags", "",
sprintf("Displays attempted: **%d**. ARDs written: **%d**. Displays rendered: **%d**. Hard errors: **%d**.",
        nrow(ST), sum(ST$ard), sum(ST$display), sum(nzchar(ST$error))), "",
"## Standing caveat", "",
"> This study randomized **17 subjects** (Placebo 5 / Zanomaline Low 5 / Zanomaline High 7); the",
"> efficacy set is 13 and the completers set is 3. Every LS-mean, contrast, CMH statistic and",
"> log-rank p-value produced here is **illustrative of the pipeline, not evidence about the drug**.",
"> Where a statistic was not estimable it is reported as `-`; no value has been substituted,",
"> approximated or fabricated to fill a cell.", "",
"## Per-display messages", "")
if (nrow(IS)) {
  I <- c(I, "| ID | Severity | Message |", "|---|---|---|",
         sprintf("| %s | %s | %s |", IS$id, IS$severity, gsub("\\|", "/", IS$msg)))
} else I <- c(I, "*(none)*")
I <- c(I, "", "## Data-provenance flags carried onto the displays", "",
"| Display | Flag |", "|---|---|",
"| T-14-3.01 | Analysis values are largely **LOCF-imputed** — the table face carries an explicit `n observed / n LOCF-imputed` row (critic finding R-2). |",
"| T-14-3.02 | Same LOCF dependency as T-14-3.01. |",
"| T-14-3.01/.02/.03 | **`SITEGR1` dropped from the ANCOVA model.** MANDATORY RULE 3 pooled all 6 sites into group 900 on randomized counts, leaving a single-level, rank-deficient factor. Each display footnotes the refit. |",
"| T-14-3.04 | MMRM covariance structure is recorded on the display; if the specified unstructured form did not converge, the fallback used is named and the non-convergence is stated rather than the table being dropped. |",
"| T-14-6.03 | **Cannot be populated.** The clinically-significant-change criterion is undefined by protocol and SAP (SD-4); `CSCFL` is all-missing by review decision. The display states this instead of inventing a threshold. |",
"| T-14-6.04/.05 | **CMH is frequently non-estimable** at 17 subjects; non-estimable p-values render as `-` with a footnote. |",
"| T-14-6.06 | **0 subjects meet Hy's Law.** A genuine negative finding. The display also shows the maximum observed multiple of ULN per analyte so the reader can see the distance from threshold. |",
"| T-14-7.04 | Concomitant medications are **not WHO-DD coded**; summarized by verbatim term under a placeholder class (critic finding R-6). |",
"| T-14-1.04 | Medical history is **uncoded**, single term — a one-row table (critic finding R-5). |",
"| F-14-1 | Injection-site reactions were collected on only **8 of 17** safety subjects; the other 9 are censored, which understates the event rate. |",
"| T-14-5.01..06 | **`AESOC` used, not `AEBODSYS`** — `AEBODSYS` is blank on all 74 AE records. |",
"| T-14-7.01/.02 | Blood pressure and pulse are reported **separately by position** (standing/supine) per USDM endpoint END4. |",
"", "## Method-engine notes", "",
"- ANCOVA LS-means and contrasts use **`emmeans::emmeans` + `emmeans::contrast` directly** with explicit coefficient lists (sign reads dose − comparator). `cardx::ard_emmeans_contrast` was not used: it returns all-NULL stats in the tested build.",
"- The dose-response test refits with the numeric dose `TRT01PN` as a **continuous** covariate and reads its coefficient p-value.",
"- MMRM has no cardx function; the ARD is hand-assembled from `mmrm::mmrm` + `emmeans`, with a documented covariance fallback ladder (unstructured → Toeplitz → compound symmetry → descriptive-only).",
"- Population N always comes from **ADSL** (one row per subject), never from a BDS dataset.")
writeLines(I, file.path(TLF_DIR, "issues.md"))
cat("wrote issues.md\n")
