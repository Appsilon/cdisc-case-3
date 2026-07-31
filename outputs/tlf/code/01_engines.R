# Name: 01_engines.R
# Description: Per-method ARD + display engines. Phase A computes into the ARD,
#              Phase B renders the ARD. The two never mix.
# ----------------------------------------------------------------------------

# Apply an analysis-spec dataSubset.condition expressed in SQL-ish text.
apply_cond <- function(d, cond) {
  if (is.null(cond) || !nzchar(cond) || grepl("^\\(", cond)) return(d)
  e <- cond
  e <- gsub(" AND ", " & ", e, fixed = TRUE); e <- gsub(" OR ", " | ", e, fixed = TRUE)
  e <- gsub(" IS NOT NULL", " %notnull%", e, fixed = TRUE)
  e <- gsub("([A-Z0-9_]+) IN \\(", "\\1 %in% c(", e)
  e <- gsub("(?<![<>!])=(?!=)", "==", e, perl = TRUE)
  e <- gsub("([A-Za-z0-9_]+) %notnull%", "!is.na(\\1)", e)
  ok <- try(eval(parse(text = e), envir = d), silent = TRUE)
  if (inherits(ok, "try-error")) stop("cannot evaluate dataSubset condition: ", cond, "\n  -> ", e)
  d[which(ok %in% TRUE), , drop = FALSE]
}

# Data-quality gate run before every table.
assert_pop <- function(ANL, spec, id, by_subject = TRUE) {
  if (nrow(ANL) == 0) { note_issue(id, "ERROR", "analysis set is empty after filtering"); return(FALSE) }
  if (anyNA(ANL$TRTP)) note_issue(id, "WARN", sprintf("%d record(s) with missing TRTP", sum(is.na(ANL$TRTP))))
  if (by_subject) {
    dup <- sum(duplicated(ANL$USUBJID))
    if (dup > 0) { note_issue(id, "ERROR", sprintf("%d duplicate subject record(s) in the analysis set", dup)); return(FALSE) }
  }
  TRUE
}

# ============================================================ Descriptive (continuous)
gen_desc_cont <- function(id, spec, vars, labels, blocks = NULL, extra_note = character(),
                          by_visit = FALSE, by_param = FALSE, digits = NULL) {
  pop <- spec$analysisSet$label; pop2 <- gsub(" Population", "", pop)
  d <- read_adam(spec$dataSubset$dataset) %>% apply_cond(spec$dataSubset$condition) %>% set_arm()
  d <- d[!is.na(d$TRTP), , drop = FALSE]
  if (!assert_pop(d, spec, id, by_subject = !by_visit && !by_param)) return(invisible(NULL))
  dig <- digits %||% c(N = 0, mean = 1, sd = 2, median = 1, min = 1, max = 1)

  grpv <- c("TRTP", if (by_param) "PARAMCD", if (by_visit) "AVISIT")
  ard <- do.call(rbind, lapply(vars, function(v) {
    d2 <- d[!is.na(d[[v]]), , drop = FALSE]
    if (!nrow(d2)) return(NULL)
    do.call(rbind, lapply(split(d2, lapply(grpv, function(g) d2[[g]]), drop = TRUE), function(s) {
      if (!nrow(s)) return(NULL)
      x <- s[[v]]
      lvl <- paste(vapply(grpv[-1], function(g) as.character(s[[g]][1]), character(1)), collapse = " | ")
      rbind(
        ard_row(s$TRTP[1], v, lvl, "descriptive", "N", sum(!is.na(x))),
        ard_row(s$TRTP[1], v, lvl, "descriptive", "mean", mean(x, na.rm = TRUE)),
        ard_row(s$TRTP[1], v, lvl, "descriptive", "sd", stats::sd(x, na.rm = TRUE)),
        ard_row(s$TRTP[1], v, lvl, "descriptive", "median", stats::median(x, na.rm = TRUE)),
        ard_row(s$TRTP[1], v, lvl, "descriptive", "min", min(x, na.rm = TRUE)),
        ard_row(s$TRTP[1], v, lvl, "descriptive", "max", max(x, na.rm = TRUE)))
    }))
  }))
  write_ard(ard, id)

  # ---- Phase B: render from the ARD
  lvls <- unique(ard$variable_level)
  L <- md_head(spec, pop2, extra_note)
  H <- c("Statistic", hdr1(pop2)[1:3])
  rows <- list()
  for (lv in lvls) for (v in vars) {
    sub <- ard[ard$variable == v & ard$variable_level == lv, , drop = FALSE]
    if (!nrow(sub)) next
    ttl <- paste0(labels[[v]] %||% v, if (nzchar(lv) && lv != "NA") paste0(" — ", lv) else "")
    rows[[length(rows) + 1]] <- c(paste0("**", ttl, "**"), "", "", "")
    g <- function(a, s) get_stat(sub, group1 = a, stat_name = s)
    rows[[length(rows) + 1]] <- c("n", vapply(ARMS, function(a) fmt(g(a, "N"), 0), character(1)))
    rows[[length(rows) + 1]] <- c("Mean (SD)", vapply(ARMS, function(a)
      sprintf("%s (%s)", fmt(g(a, "mean"), dig[["mean"]]), fmt(g(a, "sd"), dig[["sd"]])), character(1)))
    rows[[length(rows) + 1]] <- c("Median", vapply(ARMS, function(a) fmt(g(a, "median"), dig[["median"]]), character(1)))
    rows[[length(rows) + 1]] <- c("Range", vapply(ARMS, function(a)
      sprintf("(%s, %s)", fmt(g(a, "min"), dig[["min"]]), fmt(g(a, "max"), dig[["max"]])), character(1)))
  }
  write_display(c(L, md_table(H, rows), md_foot(spec, spec$notes)), id)
}

# ============================================================ Categorical frequency
gen_cat_freq <- function(id, spec, vars, labels, dataset = NULL, denom_pop = NULL,
                         extra_note = character()) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  d <- read_adam(dataset %||% spec$dataSubset$dataset) %>% apply_cond(spec$dataSubset$condition)
  d$TRTP <- factor(d$TRT01P %||% d$TRTP, levels = ARMS)
  d <- d[!is.na(d$TRTP), , drop = FALSE]
  if (!assert_pop(d, spec, id)) return(invisible(NULL))
  den <- pop_n(denom_pop %||% pop)

  ard <- do.call(rbind, lapply(vars, function(v) {
    x <- d[[v]]; x[is.na(x) | x == ""] <- "Missing"
    do.call(rbind, lapply(sort(unique(x)), function(lv)
      do.call(rbind, lapply(ARMS, function(a) {
        n <- sum(x == lv & d$TRTP == a)
        rbind(ard_row(a, v, lv, "frequency", "n", n),
              ard_row(a, v, lv, "frequency", "pct", if (den[[a]] > 0) 100 * n / den[[a]] else NA))
      }))))
  }))
  write_ard(ard, id)

  L <- md_head(spec, pop, extra_note)
  H <- c("Category", hdr1(pop)[1:3])
  rows <- list()
  for (v in vars) {
    rows[[length(rows) + 1]] <- c(paste0("**", labels[[v]] %||% v, "**"), "", "", "")
    for (lv in unique(ard$variable_level[ard$variable == v])) {
      rows[[length(rows) + 1]] <- c(paste0("&nbsp;&nbsp;", lv), vapply(ARMS, function(a) {
        n <- get_stat(ard, group1 = a, variable = v, variable_level = lv, stat_name = "n")
        p <- get_stat(ard, group1 = a, variable = v, variable_level = lv, stat_name = "pct")
        sprintf("%s (%s%%)", fmt(n, 0), fmt(p, 1)) }, character(1)))
    }
  }
  write_display(c(L, md_table(H, rows), md_foot(spec, spec$notes)), id)
}

# ============================================================ Incidence (SOC / PT)
gen_incidence <- function(id, spec, soc = "AESOC", pt = "AEDECOD", dataset = NULL,
                          extra_group = NULL, extra_note = character(), count_events = TRUE) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  d <- read_adam(dataset %||% spec$dataSubset$dataset) %>% apply_cond(spec$dataSubset$condition)
  d$TRTP <- factor(d$TRTP, levels = ARMS); d <- d[!is.na(d$TRTP), , drop = FALSE]
  den <- pop_n(pop)
  if (nrow(d) == 0) {
    note_issue(id, "INFO", "no records meet the analysis condition — rendering an all-zero table")
    ard <- do.call(rbind, lapply(ARMS, function(a) ard_row(a, "OVERALL", "Any event", "incidence", "n_subjects", 0)))
    write_ard(ard, id)
    L <- md_head(spec, pop, extra_note)
    write_display(c(L, md_table(c("System Organ Class / Preferred Term", hdr1(pop)[1:3]),
                                list(c("Subjects with at least one event", rep("0 (0.0%)", 3)))),
                    md_foot(spec, c(spec$notes, "No records met the analysis condition; the table is genuinely empty."))), id)
    return(invisible(NULL))
  }
  keyv <- c(soc, pt, extra_group)
  # overall "any event" row
  ard <- do.call(rbind, lapply(ARMS, function(a) {
    ns <- n_distinct(d$USUBJID[d$TRTP == a])
    rbind(ard_row(a, "OVERALL", "Any event", "incidence", "n_subjects", ns),
          ard_row(a, "OVERALL", "Any event", "incidence", "pct_subjects", if (den[[a]] > 0) 100 * ns / den[[a]] else NA),
          ard_row(a, "OVERALL", "Any event", "incidence", "n_events", sum(d$TRTP == a)))
  }))
  for (s in sort(unique(d[[soc]]))) {
    ds <- d[d[[soc]] == s, , drop = FALSE]
    for (a in ARMS) {
      ns <- n_distinct(ds$USUBJID[ds$TRTP == a])
      ard <- rbind(ard,
        ard_row(a, "SOC", s, "incidence", "n_subjects", ns),
        ard_row(a, "SOC", s, "incidence", "pct_subjects", if (den[[a]] > 0) 100 * ns / den[[a]] else NA),
        ard_row(a, "SOC", s, "incidence", "n_events", sum(ds$TRTP == a)))
    }
    for (p in sort(unique(ds[[pt]]))) {
      dp <- ds[ds[[pt]] == p, , drop = FALSE]
      for (g in (if (is.null(extra_group)) NA_character_ else sort(unique(dp[[extra_group]])))) {
        dg <- if (is.na(g)) dp else dp[dp[[extra_group]] == g, , drop = FALSE]
        lab <- if (is.na(g)) p else paste0(p, " [", g, "]")
        for (a in ARMS) {
          ns <- n_distinct(dg$USUBJID[dg$TRTP == a])
          ard <- rbind(ard,
            ard_row(a, paste0("PT|", s), lab, "incidence", "n_subjects", ns),
            ard_row(a, paste0("PT|", s), lab, "incidence", "pct_subjects", if (den[[a]] > 0) 100 * ns / den[[a]] else NA),
            ard_row(a, paste0("PT|", s), lab, "incidence", "n_events", sum(dg$TRTP == a)))
        }
      }
    }
  }
  write_ard(ard, id)

  cell <- function(a, var, lv) {
    n <- get_stat(ard, group1 = a, variable = var, variable_level = lv, stat_name = "n_subjects")
    p <- get_stat(ard, group1 = a, variable = var, variable_level = lv, stat_name = "pct_subjects")
    e <- get_stat(ard, group1 = a, variable = var, variable_level = lv, stat_name = "n_events")
    if (count_events) sprintf("%s (%s%%) [%s]", fmt(n, 0), fmt(p, 1), fmt(e, 0))
    else sprintf("%s (%s%%)", fmt(n, 0), fmt(p, 1))
  }
  L <- md_head(spec, pop, extra_note)
  rows <- list(c("**Subjects with at least one event**",
                 vapply(ARMS, cell, character(1), var = "OVERALL", lv = "Any event")))
  for (s in sort(unique(d[[soc]]))) {
    rows[[length(rows) + 1]] <- c(paste0("**", s, "**"), vapply(ARMS, cell, character(1), var = "SOC", lv = s))
    for (lv in unique(ard$variable_level[ard$variable == paste0("PT|", s)]))
      rows[[length(rows) + 1]] <- c(paste0("&nbsp;&nbsp;", lv),
                                    vapply(ARMS, cell, character(1), var = paste0("PT|", s), lv = lv))
  }
  write_display(c(L, md_table(c("System Organ Class / Preferred Term", hdr1(pop)[1:3]), rows),
                  md_foot(spec, c(spec$notes,
                    if (count_events) "Cells show n (%) subjects [number of events]." else "Cells show n (%) subjects."))), id)
}

`%||%` <- function(a, b) if (is.null(a)) b else a
