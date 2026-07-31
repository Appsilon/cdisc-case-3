# Name: 03_engines_shift_km.R
# Description: Shift-table (+CMH), Kaplan-Meier figure, and listing engines.
suppressPackageStartupMessages(library(patchwork))
# ----------------------------------------------------------------------------

RIND <- c("LOW", "NORMAL", "HIGH", "ABNORMAL")

# ============================================================ Shift tables
gen_shift <- function(id, spec, from = "BNRIND", to = "ANRIND", by_visit = FALSE,
                      cmh = FALSE, extra_note = character(), na_criterion = FALSE) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  d <- read_adam(spec$dataSubset$dataset) %>% apply_cond(spec$dataSubset$condition) %>% set_arm()
  d <- d[!is.na(d$TRTP), , drop = FALSE]

  if (na_criterion) {
    # SD-4: the clinically-significant-change criterion is defined by neither the
    # protocol nor any SAP. CSCFL is all-missing by human-review decision. We emit
    # the table shell with an explicit statement rather than inventing a threshold.
    note_issue(id, "INFO", "CSCFL is all-missing (SD-4: criterion unspecified) — shell emitted with an explicit footnote, no invented threshold")
    ard <- ard_row(NA, "CSCFL", "criterion undefined", "shift", "n", NA)
    write_ard(rbind(ard, ard_row(NA, "CSCFL", "criterion undefined", "shift", "records_available", nrow(d))), id)
    write_display(c(md_head(spec, pop, extra_note),
      "> **THIS TABLE CANNOT BE POPULATED.**", ">",
      "> The 'clinically significant change from the previous visit' criterion is defined by",
      "> neither the study protocol nor any SAP available to this run, and SDTM `LB` carries no",
      "> clinical-significance flag. `ADLB.CSCFL` is therefore derived as **all-missing** by the",
      "> review decision of 2026-07-29 (spec dependency **SD-4**).", ">",
      sprintf("> %d analysis records are available and would populate this table immediately once a", nrow(d)),
      "> criterion is supplied. No threshold has been invented to fill the cells.",
      md_foot(spec, c(spec$notes, "**Action required:** obtain the clinically-significant-change criterion from the sponsor."))), id)
    return(invisible(NULL))
  }

  d <- d[!is.na(d[[from]]) & !is.na(d[[to]]), , drop = FALSE]
  if (nrow(d) == 0) {
    note_issue(id, "WARN", "no records with both a baseline and a post-baseline reference-range indicator")
    write_ard(ard_row(NA, "SHIFT", "none", "shift", "n", 0), id)
    write_display(c(md_head(spec, pop, extra_note), "**No shiftable records.**", md_foot(spec, spec$notes)), id)
    return(invisible(NULL))
  }
  d[[from]] <- factor(d[[from]], levels = RIND); d[[to]] <- factor(d[[to]], levels = RIND)
  strata <- if (by_visit) sort(unique(d$AVISIT)) else "Overall"
  ard <- NULL
  for (st in strata) {
    ds <- if (by_visit) d[d$AVISIT == st, , drop = FALSE] else d
    for (a in ARMS) {
      da <- ds[ds$TRTP == a, , drop = FALSE]
      tb <- table(droplevels(da[[from]], exclude = NULL), droplevels(da[[to]], exclude = NULL))
      if (!length(tb)) next
      for (r in rownames(tb)) for (cc in colnames(tb))
        ard <- rbind(ard, ard_row(a, paste0(st, "|", r), cc, "shift", "n", tb[r, cc]))
    }
    if (cmh) {
      tab <- try(table(ds$TRTP, ds[[to]], ds[[from]]), silent = TRUE)
      p <- NA_real_
      if (!inherits(tab, "try-error")) {
        keep <- apply(tab, 3, function(m) sum(m) > 0 && nrow(m) > 1 && ncol(m) > 1)
        if (any(keep)) {
          r <- try(suppressWarnings(stats::mantelhaen.test(tab[, , keep, drop = FALSE], exact = FALSE)), silent = TRUE)
          if (!inherits(r, "try-error")) p <- r$p.value
        }
      }
      if (is.na(p)) note_issue(id, "WARN",
        sprintf("CMH p-value not estimable for stratum '%s' — sparse strata (17 subjects). Reported as NA, not fabricated.", st))
      ard <- rbind(ard, ard_row(NA, paste0(st, "|CMH"), "Cochran-Mantel-Haenszel", "cmh", "p.value", p))
    }
  }
  write_ard(ard, id)

  L <- md_head(spec, pop, extra_note)
  body <- c()
  for (st in strata) {
    if (by_visit) body <- c(body, "", paste0("#### ", st), "")
    rows <- list()
    for (a in ARMS) {
      rows[[length(rows) + 1]] <- c(paste0("**", a, "**"), rep("", length(RIND)))
      for (r in RIND) {
        cells <- vapply(RIND, function(cc) {
          n <- get_stat(ard, group1 = a, variable = paste0(st, "|", r), variable_level = cc, stat_name = "n")
          if (is.na(n)) "0" else fmt(n, 0) }, character(1))
        if (all(cells == "0")) next
        rows[[length(rows) + 1]] <- c(paste0("&nbsp;&nbsp;Baseline ", r), cells)
      }
    }
    body <- c(body, md_table(c("Baseline -> Post-baseline", RIND), rows))
    if (cmh) {
      p <- get_stat(ard, variable = paste0(st, "|CMH"), stat_name = "p.value")
      body <- c(body, "", sprintf("Cochran-Mantel-Haenszel p-value: **%s**%s", fmtp(p),
        if (is.na(p)) "  *(not estimable — see notes)*" else ""))
    }
  }
  notes <- c(spec$notes, "Cells are record counts of baseline category (rows) against post-baseline category (columns).")
  if (cmh) notes <- c(notes,
    "**Sparse strata.** With 17 subjects the CMH test is frequently non-estimable. Where that happens the p-value is reported as `-` (not estimable). No value is substituted or approximated.")
  write_display(c(L, body, md_foot(spec, notes)), id)
}

# ============================================================ Kaplan-Meier figure
gen_km <- function(id, spec, extra_note = character()) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  d <- read_adam(spec$dataSubset$dataset) %>% apply_cond(spec$dataSubset$condition) %>% set_arm()
  d <- d[!is.na(d$TRTP) & !is.na(d$AVAL), , drop = FALSE]
  if (!assert_pop(d, spec, id)) return(invisible(NULL))
  d$EVENT <- 1 - d$CNSR
  note_issue(id, "INFO", sprintf("%d subjects, %d events, %d censored", nrow(d), sum(d$EVENT == 1), sum(d$EVENT == 0)))

  sf <- survival::survfit(survival::Surv(AVAL, EVENT) ~ TRTP, data = d)
  smry <- summary(sf)$table
  if (is.null(dim(smry))) smry <- t(as.matrix(smry))
  rn <- gsub("^TRTP=", "", rownames(smry))
  ard <- NULL
  for (i in seq_along(rn)) {
    a <- rn[i]
    g <- function(k) if (k %in% colnames(smry)) as.numeric(smry[i, k]) else NA_real_
    ard <- rbind(ard,
      ard_row(a, "SURVIVAL", NA, "km", "n", g("records")),
      ard_row(a, "SURVIVAL", NA, "km", "n_event", g("events")),
      ard_row(a, "SURVIVAL", NA, "km", "n_censor", g("records") - g("events")),
      ard_row(a, "SURVIVAL", NA, "km", "median", g("median")),
      ard_row(a, "SURVIVAL", NA, "km", "median_lcl", g("0.95LCL")),
      ard_row(a, "SURVIVAL", NA, "km", "median_ucl", g("0.95UCL")))
  }
  lr <- try(survival::survdiff(survival::Surv(AVAL, EVENT) ~ TRTP, data = d), silent = TRUE)
  p <- if (inherits(lr, "try-error")) NA_real_ else 1 - stats::pchisq(lr$chisq, length(lr$n) - 1)
  ard <- rbind(ard, ard_row(NA, "LOGRANK", "across treatment groups", "logrank", "p.value", p))

  # ---- Phase B: ggsurvfit, 300 dpi PNG with a number-at-risk table
  # NOTE: ggsurvfit::add_risktable() errors under this ggsurvfit 1.1.0 /
  # ggplot2 4.0.2.9000 combination (.construct_risktable: "argument
  # 'risktable_height' is missing", raised even when the argument IS supplied).
  # The number-at-risk table is therefore built as a second panel and composed
  # with patchwork, rather than dropping it from the figure.
  dd <- file.path(TLF_DIR, id); dir.create(dd, showWarnings = FALSE, recursive = TRUE)
  brks <- seq(0, ceiling(max(d$AVAL, na.rm = TRUE) / 25) * 25, 25)
  atrisk <- do.call(rbind, lapply(ARMS, function(a) {
    x <- d$AVAL[d$TRTP == a]
    data.frame(TRTP = a, time = brks,
               n = vapply(brks, function(t) sum(x >= t, na.rm = TRUE), integer(1)),
               stringsAsFactors = FALSE)
  }))
  atrisk$TRTP <- factor(atrisk$TRTP, levels = rev(ARMS))
  for (i in seq_len(nrow(atrisk)))
    ard <- rbind(ard, ard_row(as.character(atrisk$TRTP[i]), "ATRISK",
                              paste0("day ", atrisk$time[i]), "km", "n_at_risk", atrisk$n[i]))
  write_ard(ard, id)

  ok_png <- TRUE
  gg <- try({
    fit2 <- ggsurvfit::survfit2(survival::Surv(AVAL, EVENT) ~ TRTP, data = d)
    pl <- ggsurvfit::ggsurvfit(fit2, linewidth = 0.9) +
      ggsurvfit::add_censor_mark(size = 2.4, alpha = 0.9) +
      ggplot2::scale_y_continuous(limits = c(0, 1), expand = c(0.01, 0)) +
      ggplot2::scale_x_continuous(breaks = brks, limits = range(brks)) +
      ggplot2::labs(x = NULL, y = "Probability of remaining event-free",
                    title = spec$title,
                    subtitle = sprintf("%s population (N=%d)  |  log-rank p = %s",
                                       gsub(" Population", "", spec$analysisSet$label), nrow(d), fmtp(p))) +
      ggplot2::theme_minimal(base_size = 12) +
      ggplot2::theme(legend.position = "top", legend.title = ggplot2::element_blank(),
                     panel.grid.minor = ggplot2::element_blank())
    rt <- ggplot2::ggplot(atrisk, ggplot2::aes(x = time, y = TRTP, label = n)) +
      ggplot2::geom_text(size = 3.4) +
      ggplot2::scale_x_continuous(breaks = brks, limits = range(brks)) +
      ggplot2::labs(x = "Days since first dose", y = NULL, title = "Number at risk") +
      ggplot2::theme_minimal(base_size = 12) +
      ggplot2::theme(panel.grid = ggplot2::element_blank(),
                     plot.title = ggplot2::element_text(size = 10, face = "plain"),
                     axis.text.y = ggplot2::element_text(hjust = 0))
    comb <- patchwork::wrap_plots(pl, rt, ncol = 1, heights = c(3.2, 1)) +
      patchwork::plot_annotation(caption = "Illustrative only: 17 randomized subjects.")
    ggplot2::ggsave(file.path(dd, paste0(id, ".png")), comb, width = 10, height = 7, dpi = 300)
    TRUE }, silent = TRUE)
  if (inherits(gg, "try-error")) {
    ok_png <- FALSE
    note_issue(id, "WARN", paste("figure render failed:", trimws(gsub("\\s+", " ", as.character(gg)))))
  } else cat(sprintf("    figure -> %s/%s.png (300 dpi, with number-at-risk panel)\n", id, id))

  L <- md_head(spec, pop, extra_note)
  rows <- lapply(ARMS, function(a) {
    g <- function(s) get_stat(ard, group1 = a, variable = "SURVIVAL", stat_name = s)
    n <- g("n"); ev <- g("n_event"); cn <- g("n_censor")
    c(a, fmt(n, 0),
      sprintf("%s (%s%%)", fmt(ev, 0), fmt(if (!is.na(n) && n > 0) 100 * ev / n else NA, 1)),
      sprintf("%s (%s%%)", fmt(cn, 0), fmt(if (!is.na(n) && n > 0) 100 * cn / n else NA, 1)),
      if (is.na(g("median"))) "NE" else fmt(g("median"), 1),
      sprintf("(%s, %s)", if (is.na(g("median_lcl"))) "NE" else fmt(g("median_lcl"), 1),
              if (is.na(g("median_ucl"))) "NE" else fmt(g("median_ucl"), 1)))
  })
  write_display(c(L,
    if (ok_png) c(sprintf("![%s](%s.png)", spec$title, id), "") else
      c("*(figure render failed — see issues.md; the summary statistics below still come from the ARD)*", ""),
    "#### Summary statistics", "",
    md_table(c("Treatment group", "N", "Events", "Censored", "Median (days)", "95% CI"), rows), "",
    sprintf("Log-rank p-value across treatment groups: **%s**", fmtp(p)),
    md_foot(spec, c(spec$notes,
      "NE = not estimable (median not reached).",
      "The figure carries a number-at-risk panel beneath the curves, built manually: `ggsurvfit::add_risktable()` errors under the installed ggsurvfit 1.1.0 / ggplot2 4.0.2.9000 combination. At-risk counts are in the ARD (`stat_name = n_at_risk`)."))), id)
}

# ============================================================ Listing
gen_listing <- function(id, spec, cols, labels, join_ae = FALSE, extra_note = character()) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  d <- read_adam(spec$dataSubset$dataset) %>% apply_cond(spec$dataSubset$condition)
  if (join_ae) {
    ae <- read_adam("ADAE")
    ae <- ae[ae$AEOUT == "FATAL", c("USUBJID", "AEDECOD", "AESOC"), drop = FALSE]
    ae <- ae[!duplicated(ae$USUBJID), , drop = FALSE]
    d <- merge(d, ae, by = "USUBJID", all.x = TRUE)
  }
  cols <- cols[cols %in% names(d)]
  d <- d[order(d$USUBJID), cols, drop = FALSE]
  note_issue(id, "INFO", sprintf("listing: %d row(s)", nrow(d)))
  # A listing has no statistics; the ARD records provenance and the row count.
  write_ard(rbind(ard_row(NA, "LISTING", "rows", "listing", "n_rows", nrow(d)),
                  ard_row(NA, "LISTING", "columns", "listing", "n_cols", length(cols))), id)
  hdrs <- vapply(cols, function(c0) labels[[c0]] %||% c0, character(1))
  rows <- lapply(seq_len(nrow(d)), function(i)
    vapply(cols, function(c0) { v <- d[i, c0]; if (is.na(v) || v == "") "-" else as.character(v) }, character(1)))
  write_display(c(md_head(spec, pop, extra_note), md_table(hdrs, rows),
    md_foot(spec, c(spec$notes, "Listings present subject-level records; no statistic is computed."))), id)
}
