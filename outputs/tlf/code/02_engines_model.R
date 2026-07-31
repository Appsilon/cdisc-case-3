# Name: 02_engines_model.R
# Description: Model-based engines — ANCOVA + LS-means + dose-response, MMRM,
#              shift tables (+ CMH), Kaplan-Meier, and listings.
# ----------------------------------------------------------------------------

# ============================================================ ANCOVA
# Uses emmeans DIRECTLY. cardx::ard_emmeans_contrast returns all-NULL stats in
# the tested build and must not be used. Contrast coefficients are passed
# explicitly so the sign reads dose - reference.
gen_ancova <- function(id, spec, extra_note = character()) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  raw <- read_adam(spec$dataSubset$dataset)
  d <- raw %>% apply_cond(spec$dataSubset$condition) %>% set_arm()
  d <- d[!is.na(d$TRTP) & !is.na(d$CHG) & !is.na(d$BASE), , drop = FALSE]
  if (!assert_pop(d, spec, id)) return(invisible(NULL))
  d$SITEGR1 <- factor(d$SITEGR1)
  nobs <- sum(is.na(d$DTYPE) | d$DTYPE == "")
  nlocf <- sum(!is.na(d$DTYPE) & d$DTYPE == "LOCF")
  note_issue(id, "INFO", sprintf("analysis n=%d (observed %d, LOCF-imputed %d)", nrow(d), nobs, nlocf))

  # --- descriptives into the ARD
  ard <- do.call(rbind, lapply(c("BASE", "AVAL", "CHG"), function(v)
    do.call(rbind, lapply(ARMS, function(a) {
      x <- d[[v]][d$TRTP == a]
      if (!length(x)) return(NULL)
      rbind(ard_row(a, v, NA, "descriptive", "N", sum(!is.na(x))),
            ard_row(a, v, NA, "descriptive", "mean", mean(x, na.rm = TRUE)),
            ard_row(a, v, NA, "descriptive", "sd", stats::sd(x, na.rm = TRUE)),
            ard_row(a, v, NA, "descriptive", "median", stats::median(x, na.rm = TRUE)),
            ard_row(a, v, NA, "descriptive", "min", min(x, na.rm = TRUE)),
            ard_row(a, v, NA, "descriptive", "max", max(x, na.rm = TRUE)))
    }))))
  # observed-vs-imputed counts on the table face (critic finding R-2)
  for (a in ARMS) {
    ard <- rbind(ard,
      ard_row(a, "PROVENANCE", NA, "provenance", "n_observed",
              sum(d$TRTP == a & (is.na(d$DTYPE) | d$DTYPE == ""))),
      ard_row(a, "PROVENANCE", NA, "provenance", "n_locf",
              sum(d$TRTP == a & !is.na(d$DTYPE) & d$DTYPE == "LOCF")))
  }

  # --- model, with the SITEGR1 fallback ladder
  usesite <- nlevels(droplevels(d$SITEGR1)) >= 2
  form <- if (usesite) CHG ~ TRTP + SITEGR1 + BASE else CHG ~ TRTP + BASE
  if (!usesite) note_issue(id, "WARN",
    paste("SITEGR1 has a single level (all sites pooled to 900 by MANDATORY RULE 3) and is",
          "rank-deficient; the model was refitted as CHG ~ TRTP + BASE. Recorded on the display."))
  fit <- try(stats::lm(form, data = d), silent = TRUE)
  narm <- length(unique(d$TRTP[!is.na(d$CHG)]))
  if (inherits(fit, "try-error") || narm < 2) {
    note_issue(id, "ERROR", "ANCOVA not estimable; emitting descriptives only")
    write_ard(ard, id)
    write_display(c(md_head(spec, pop, extra_note), "**ANCOVA not estimable at this sample size.**",
                    md_foot(spec, spec$notes)), id)
    return(invisible(NULL))
  }
  emm <- try(emmeans::emmeans(fit, ~ TRTP), silent = TRUE)
  ok_emm <- !inherits(emm, "try-error")
  if (ok_emm) {
    es <- as.data.frame(emm)
    for (i in seq_len(nrow(es))) {
      a <- as.character(es$TRTP[i])
      ard <- rbind(ard,
        ard_row(a, "LSMEAN", NA, "ancova", "lsmean", es$emmean[i]),
        ard_row(a, "LSMEAN", NA, "ancova", "lsmean_se", es$SE[i]))
    }
    lv <- levels(droplevels(d$TRTP)); idx <- setNames(seq_along(lv), lv)
    cf <- list()
    mk <- function(from, to) { v <- rep(0, length(lv)); v[idx[[from]]] <- -1; v[idx[[to]]] <- 1; v }
    if (all(c(ARMS[1], ARMS[2]) %in% lv)) cf[["Zanomaline Low Dose - Placebo"]]  <- mk(ARMS[1], ARMS[2])
    if (all(c(ARMS[1], ARMS[3]) %in% lv)) cf[["Zanomaline High Dose - Placebo"]] <- mk(ARMS[1], ARMS[3])
    if (all(c(ARMS[2], ARMS[3]) %in% lv)) cf[["Zanomaline High Dose - Zanomaline Low Dose"]] <- mk(ARMS[2], ARMS[3])
    ct <- try(as.data.frame(emmeans::contrast(emm, method = cf, infer = c(TRUE, TRUE))), silent = TRUE)
    if (!inherits(ct, "try-error")) for (i in seq_len(nrow(ct))) {
      cn <- as.character(ct$contrast[i])
      ard <- rbind(ard,
        ard_row(NA, "CONTRAST", cn, "ancova", "diff", ct$estimate[i]),
        ard_row(NA, "CONTRAST", cn, "ancova", "diff_se", ct$SE[i]),
        ard_row(NA, "CONTRAST", cn, "ancova", "conf.low", ct$lower.CL[i]),
        ard_row(NA, "CONTRAST", cn, "ancova", "conf.high", ct$upper.CL[i]),
        ard_row(NA, "CONTRAST", cn, "ancova", "p.value", ct$p.value[i]))
    }
  }
  # --- dose-response: numeric dose as a CONTINUOUS covariate
  dform <- if (usesite) CHG ~ TRT01PN + SITEGR1 + BASE else CHG ~ TRT01PN + BASE
  dfit <- try(stats::lm(dform, data = d), silent = TRUE)
  if (!inherits(dfit, "try-error")) {
    co <- summary(dfit)$coefficients
    if ("TRT01PN" %in% rownames(co)) {
      ard <- rbind(ard,
        ard_row(NA, "DOSERESPONSE", "TRT01PN (continuous dose)", "doseresponse", "estimate", co["TRT01PN", "Estimate"]),
        ard_row(NA, "DOSERESPONSE", "TRT01PN (continuous dose)", "doseresponse", "p.value", co["TRT01PN", "Pr(>|t|)"]))
    }
  }
  write_ard(ard, id)

  # ---- Phase B
  L <- md_head(spec, pop, extra_note)
  H <- c("Statistic", hdr1(pop)[1:3])
  rows <- list()
  blk <- function(v, ttl) {
    rows[[length(rows) + 1]] <<- c(paste0("**", ttl, "**"), "", "", "")
    g <- function(a, s) get_stat(ard, group1 = a, variable = v, stat_name = s)
    rows[[length(rows) + 1]] <<- c("n", vapply(ARMS, function(a) fmt(g(a, "N"), 0), character(1)))
    rows[[length(rows) + 1]] <<- c("Mean (SD)", vapply(ARMS, function(a)
      sprintf("%s (%s)", fmt(g(a, "mean"), 1), fmt(g(a, "sd"), 2)), character(1)))
    rows[[length(rows) + 1]] <<- c("Median", vapply(ARMS, function(a) fmt(g(a, "median"), 1), character(1)))
    rows[[length(rows) + 1]] <<- c("Range", vapply(ARMS, function(a)
      sprintf("(%s, %s)", fmt(g(a, "min"), 1), fmt(g(a, "max"), 1)), character(1)))
  }
  # data-provenance row demanded by critic finding R-2
  rows[[length(rows) + 1]] <- c("**Data provenance**", "", "", "")
  rows[[length(rows) + 1]] <- c("n observed / n LOCF-imputed", vapply(ARMS, function(a)
    sprintf("%s / %s", fmt(get_stat(ard, group1 = a, variable = "PROVENANCE", stat_name = "n_observed"), 0),
            fmt(get_stat(ard, group1 = a, variable = "PROVENANCE", stat_name = "n_locf"), 0)), character(1)))
  blk("BASE", "Baseline"); blk("AVAL", "Week 24"); blk("CHG", "Change from Baseline")
  if (ok_emm) {
    rows[[length(rows) + 1]] <- c("**ANCOVA (LS-means)**", "", "", "")
    rows[[length(rows) + 1]] <- c("LS Mean (SE)", vapply(ARMS, function(a)
      sprintf("%s (%s)", fmt(get_stat(ard, group1 = a, variable = "LSMEAN", stat_name = "lsmean"), 1),
              fmt(get_stat(ard, group1 = a, variable = "LSMEAN", stat_name = "lsmean_se"), 2)), character(1)))
  }
  cnames <- unique(ard$variable_level[ard$variable == "CONTRAST"])
  ctab <- NULL
  if (length(cnames)) {
    ctab <- c("", "#### Pairwise comparisons", "",
      md_table(c("Comparison", "Diff of LS Means (SE)", "95% CI", "p-value"),
        lapply(cnames, function(cn) c(cn,
          sprintf("%s (%s)", fmt(get_stat(ard, variable = "CONTRAST", variable_level = cn, stat_name = "diff"), 1),
                  fmt(get_stat(ard, variable = "CONTRAST", variable_level = cn, stat_name = "diff_se"), 2)),
          sprintf("(%s, %s)", fmt(get_stat(ard, variable = "CONTRAST", variable_level = cn, stat_name = "conf.low"), 1),
                  fmt(get_stat(ard, variable = "CONTRAST", variable_level = cn, stat_name = "conf.high"), 1)),
          fmtp(get_stat(ard, variable = "CONTRAST", variable_level = cn, stat_name = "p.value"))))))
  }
  dp <- get_stat(ard, variable = "DOSERESPONSE", stat_name = "p.value")
  dr <- if (!is.na(dp)) c("", sprintf("**Dose-response (continuous dose) p-value: %s**", fmtp(dp))) else NULL
  popN <- pop_n(pop)[["Total"]]
  notes <- c(spec$notes,
    if (nrow(d) != popN) sprintf(
      paste("**Denominator note.** The %s population is N=%d, but this analysis has n=%d.",
            "The difference is not a dropped record: the population flag spans all three delivered",
            "efficacy instruments (PHQ-9, SWLS, AVLT-REY), whereas this table requires a non-missing",
            "baseline AND a Week-24 analysis value for THIS parameter specifically. The per-arm 'n'",
            "rows above are the analysis denominators; the column headers show the population size."),
      pop, popN, nrow(d)) else NULL,
    sprintf("Model: `%s`. LS-means via `emmeans::emmeans` with equal reference-grid weighting (the SAS LSMEANS default); contrasts via `emmeans::contrast` with explicit coefficient lists so each difference reads dose - comparator.",
            paste(deparse(form), collapse = "")),
    if (!usesite) "**SITEGR1 was dropped from the model**: MANDATORY RULE 3 pooled all 6 sites into group 900 on randomized counts, leaving a single-level (rank-deficient) factor. Refitted as shown above." else NULL,
    sprintf("The 'n observed / n LOCF-imputed' row is shown on the table face because %d of %d analysis values are carried forward.", nlocf, nrow(d)))
  write_display(c(L, md_table(H, rows), ctab, dr, md_foot(spec, notes)), id)
}

# ============================================================ MMRM
gen_mmrm <- function(id, spec, extra_note = character()) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  d <- read_adam(spec$dataSubset$dataset) %>% apply_cond(spec$dataSubset$condition) %>% set_arm()
  d <- d[!is.na(d$TRTP) & !is.na(d$CHG) & !is.na(d$BASE), , drop = FALSE]
  d$AVISIT <- factor(d$AVISIT); d$USUBJID <- factor(d$USUBJID)
  note_issue(id, "INFO", sprintf("observed-cases records: %d across %d subjects and %d visits",
                                 nrow(d), nlevels(d$USUBJID), nlevels(d$AVISIT)))
  # descriptive companion by visit — always produced, even if the model fails
  ard <- do.call(rbind, lapply(levels(d$AVISIT), function(vz)
    do.call(rbind, lapply(ARMS, function(a) {
      x <- d$CHG[d$AVISIT == vz & d$TRTP == a]
      if (!length(x)) return(NULL)
      rbind(ard_row(a, "CHG", vz, "descriptive", "N", length(x)),
            ard_row(a, "CHG", vz, "descriptive", "mean", mean(x)),
            ard_row(a, "CHG", vz, "descriptive", "sd", stats::sd(x)))
    }))))

  # Fallback ladder. The FIRST rung is the model the analysis spec actually
  # specifies — including the TRTP:AVISIT interaction, WITHOUT which the
  # treatment effect is forced to be constant across visits and every visit
  # reports an identical contrast (a silently wrong "MMRM"). Only if that fails
  # do we simplify, and every simplification is named on the display.
  MEAN_FULL <- "CHG ~ TRTP + AVISIT + TRTP:AVISIT + BASE + BASE:AVISIT"
  MEAN_NOBI <- "CHG ~ TRTP + AVISIT + TRTP:AVISIT + BASE"
  MEAN_ADD  <- "CHG ~ TRTP + AVISIT + BASE"
  ladder <- list(
    list("unstructured, treatment-by-visit interaction",        MEAN_FULL, "us(AVISIT | USUBJID)"),
    list("Toeplitz, treatment-by-visit interaction",            MEAN_FULL, "toep(AVISIT | USUBJID)"),
    list("compound symmetry, treatment-by-visit interaction",   MEAN_FULL, "cs(AVISIT | USUBJID)"),
    list("compound symmetry, interaction without BASE-by-visit", MEAN_NOBI, "cs(AVISIT | USUBJID)"),
    list("compound symmetry, ADDITIVE (no treatment-by-visit interaction)", MEAN_ADD, "cs(AVISIT | USUBJID)"))
  fitted <- NULL; used <- NA_character_; used_mean <- NA_character_
  for (L2 in ladder) {
    if (nlevels(d$AVISIT) < 2) break
    f <- stats::as.formula(paste(L2[[2]], "+", L2[[3]]))
    m <- try(suppressWarnings(mmrm::mmrm(formula = f, data = d,
                                         control = mmrm::mmrm_control(method = "Kenward-Roger"))),
             silent = TRUE)
    if (!inherits(m, "try-error")) {
      # A fit can "converge" and still be numerically degenerate: at this sample
      # size the saturated mean model leaves parameters unidentified, which shows
      # up as absurd standard errors (order 1e6) rather than an error. Treat that
      # as a failed rung — reporting an LS-mean with SE 8,239,108 as a result
      # would be worse than reporting non-convergence.
      chk <- try(as.data.frame(emmeans::emmeans(m, ~ TRTP | AVISIT)), silent = TRUE)
      # NA standard errors are EXPECTED here — sparse visits (Weeks 12/20 have
      # 1-2 observations) simply have no estimable cell, and that is reported as
      # "-" rather than treated as a broken model. Degeneracy means an SE that is
      # infinite, or finite but orders of magnitude beyond the response scale.
      sdy <- stats::sd(d$CHG, na.rm = TRUE)
      se  <- if (inherits(chk, "try-error")) numeric(0) else chk$SE
      bad <- inherits(chk, "try-error") || all(is.na(se)) ||
             any(is.infinite(se)) || any(se > 100 * sdy, na.rm = TRUE)
      if (!bad) { fitted <- m; used <- L2[[1]]; used_mean <- L2[[2]]; break }
      note_issue(id, "WARN", sprintf(
        "MMRM rung '%s' converged but is numerically DEGENERATE (max LS-mean SE = %s vs response SD %s); rejected, falling back",
        L2[[1]], format(suppressWarnings(max(se, na.rm = TRUE)), digits = 3, scientific = TRUE),
        format(stats::sd(d$CHG, na.rm = TRUE), digits = 3)))
    } else note_issue(id, "WARN", sprintf("MMRM rung '%s' did not converge; falling back", L2[[1]]))
  }
  if (is.null(fitted)) {
    note_issue(id, "ERROR",
      "MMRM failed to converge under unstructured, Toeplitz AND compound-symmetry covariance. Emitting the descriptive companion only, with an explicit non-convergence footnote. The table is NOT silently dropped.")
    write_ard(ard, id)
    L <- md_head(spec, pop, extra_note)
    rows <- lapply(levels(d$AVISIT), function(vz) c(vz, vapply(ARMS, function(a)
      sprintf("%s (%s) [n=%s]",
              fmt(get_stat(ard, group1 = a, variable_level = vz, stat_name = "mean"), 1),
              fmt(get_stat(ard, group1 = a, variable_level = vz, stat_name = "sd"), 2),
              fmt(get_stat(ard, group1 = a, variable_level = vz, stat_name = "N"), 0)), character(1))))
    write_display(c(L, "> **MMRM DID NOT CONVERGE.** Unstructured, Toeplitz and compound-symmetry",
      "> covariance structures were each attempted and each failed at this sample size",
      sprintf("> (%d observed records, %d subjects, %d visits). Only the observed-cases descriptive",
              nrow(d), nlevels(d$USUBJID), nlevels(d$AVISIT)),
      "> companion is shown. No model-based estimate is available for this display.", "",
      "#### Observed change from baseline by visit — mean (SD) [n]", "",
      md_table(c("Analysis visit", hdr1(pop)[1:3]), rows),
      md_foot(spec, c(spec$notes, "MMRM non-convergence is recorded in `issues.md` and in the ARD context."))), id)
    return(invisible(NULL))
  }
  note_issue(id, "INFO", sprintf("MMRM converged: %s (Kenward-Roger DoF); mean model %s", used, used_mean))
  if (identical(used_mean, MEAN_ADD)) note_issue(id, "WARN",
    paste("MMRM fell all the way back to an ADDITIVE mean model with NO treatment-by-visit",
          "interaction. The treatment effect is therefore constrained to be identical at every",
          "visit and the per-visit contrasts WILL be identical. This is a model limitation forced",
          "by the sample size, not a finding. Stated explicitly on the display."))
  emm <- try(emmeans::emmeans(fitted, ~ TRTP | AVISIT), silent = TRUE)
  if (!inherits(emm, "try-error")) {
    es <- as.data.frame(emm)
    for (i in seq_len(nrow(es))) ard <- rbind(ard,
      ard_row(as.character(es$TRTP[i]), "LSMEAN", as.character(es$AVISIT[i]), "mmrm", "lsmean", es$emmean[i]),
      ard_row(as.character(es$TRTP[i]), "LSMEAN", as.character(es$AVISIT[i]), "mmrm", "lsmean_se", es$SE[i]))
    ct <- try(as.data.frame(emmeans::contrast(emm, method = "trt.vs.ctrl", ref = 1, infer = c(TRUE, TRUE))), silent = TRUE)
    if (!inherits(ct, "try-error")) for (i in seq_len(nrow(ct))) ard <- rbind(ard,
      ard_row(NA, "CONTRAST", paste0(ct$contrast[i], " @ ", ct$AVISIT[i]), "mmrm", "diff", ct$estimate[i]),
      ard_row(NA, "CONTRAST", paste0(ct$contrast[i], " @ ", ct$AVISIT[i]), "mmrm", "diff_se", ct$SE[i]),
      ard_row(NA, "CONTRAST", paste0(ct$contrast[i], " @ ", ct$AVISIT[i]), "mmrm", "p.value", ct$p.value[i]))
  }
  write_ard(ard, id)
  L <- md_head(spec, pop, extra_note)
  vz <- levels(d$AVISIT)
  rows <- lapply(vz, function(v) c(v, vapply(ARMS, function(a) {
    lm_ <- get_stat(ard, group1 = a, variable = "LSMEAN", variable_level = v, stat_name = "lsmean")
    se <- get_stat(ard, group1 = a, variable = "LSMEAN", variable_level = v, stat_name = "lsmean_se")
    if (is.na(lm_)) "-" else sprintf("%s (%s)", fmt(lm_, 1), fmt(se, 2)) }, character(1))))
  cn <- unique(ard$variable_level[ard$variable == "CONTRAST"])
  ctab <- if (length(cn)) c("", "#### Contrasts vs Placebo", "",
    md_table(c("Comparison", "Diff of LS Means (SE)", "p-value"), lapply(cn, function(k) c(k,
      sprintf("%s (%s)", fmt(get_stat(ard, variable = "CONTRAST", variable_level = k, stat_name = "diff"), 1),
              fmt(get_stat(ard, variable = "CONTRAST", variable_level = k, stat_name = "diff_se"), 2)),
      fmtp(get_stat(ard, variable = "CONTRAST", variable_level = k, stat_name = "p.value")))))) else NULL
  write_display(c(L, "#### LS Mean change from baseline (SE) by visit", "",
    md_table(c("Analysis visit", hdr1(pop)[1:3]), rows), ctab,
    md_foot(spec, c(spec$notes,
      sprintf("Model actually fitted: `%s`, with %s covariance and Kenward-Roger degrees of freedom.",
              used_mean, sub(",.*$", "", used)),
      sprintf("Fallback ladder: the analysis spec specifies an unstructured covariance with a treatment-by-visit interaction. %s",
              if (grepl("^unstructured", used)) "That model converged and is the one reported."
              else sprintf("It did not survive at this sample size; the ladder descended to **%s**, which is what is reported above. A rung is rejected either for failing to converge OR for converging to a numerically degenerate fit — LS-mean standard errors orders of magnitude larger than the response SD, i.e. unidentified parameters.", used)),
      if (identical(used_mean, MEAN_ADD))
        paste("**WARNING — no treatment-by-visit interaction.** The mean model reduced to an additive",
              "form, so the treatment effect is constrained to be constant across visits and the",
              "per-visit contrasts below are identical by construction. They are NOT evidence of a",
              "stable effect over time; they are the same number repeated. Do not read them as",
              "per-visit estimates.") else NULL,
      "Observed cases only — LOCF records are excluded (`DTYPE = ''`), as MMRM operates under MAR."))), id)
}
