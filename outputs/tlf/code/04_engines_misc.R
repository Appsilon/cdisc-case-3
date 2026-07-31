# Name: 04_engines_misc.R
# Description: Mixed continuous+categorical demographics engine, and the
#              Hy's Law criterion table.
# ----------------------------------------------------------------------------

# ============================================================ Demographics
gen_demographics <- function(id, spec, extra_note = character()) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  d <- read_adam("ADSL") %>% apply_cond(spec$dataSubset$condition)
  d$TRTP <- factor(d$TRT01P, levels = ARMS)
  d <- d[!is.na(d$TRTP), , drop = FALSE]
  if (!assert_pop(d, spec, id)) return(invisible(NULL))
  den <- pop_n(pop)

  CONT <- c(AGE = "Age (years)", WEIGHTBL = "Baseline weight (kg)",
            HEIGHTBL = "Baseline height (cm)", BMIBL = "Baseline BMI (kg/m2)")
  CATV <- c(SEX = "Sex", AGEGR1 = "Age group", RACE = "Race", ETHNIC = "Ethnicity",
            COUNTRY = "Country")
  ard <- NULL
  for (v in names(CONT)) for (a in ARMS) {
    x <- d[[v]][d$TRTP == a]; x <- x[!is.na(x)]
    if (!length(x)) next
    ard <- rbind(ard,
      ard_row(a, v, NA, "descriptive", "N", length(x)),
      ard_row(a, v, NA, "descriptive", "mean", mean(x)),
      ard_row(a, v, NA, "descriptive", "sd", stats::sd(x)),
      ard_row(a, v, NA, "descriptive", "median", stats::median(x)),
      ard_row(a, v, NA, "descriptive", "min", min(x)),
      ard_row(a, v, NA, "descriptive", "max", max(x)))
  }
  for (v in names(CATV)) {
    x <- d[[v]]; x[is.na(x) | x == ""] <- "Missing"
    for (lv in sort(unique(x))) for (a in ARMS) {
      n <- sum(x == lv & d$TRTP == a)
      ard <- rbind(ard,
        ard_row(a, v, lv, "frequency", "n", n),
        ard_row(a, v, lv, "frequency", "pct", if (den[[a]] > 0) 100 * n / den[[a]] else NA))
    }
  }
  write_ard(ard, id)

  L <- md_head(spec, pop, extra_note)
  H <- c("Characteristic", hdr1(pop)[1:3]); rows <- list()
  for (v in names(CONT)) {
    rows[[length(rows)+1]] <- c(paste0("**", CONT[[v]], "**"), "", "", "")
    g <- function(a, s) get_stat(ard, group1 = a, variable = v, stat_name = s)
    rows[[length(rows)+1]] <- c("n", vapply(ARMS, function(a) fmt(g(a, "N"), 0), character(1)))
    rows[[length(rows)+1]] <- c("Mean (SD)", vapply(ARMS, function(a)
      sprintf("%s (%s)", fmt(g(a, "mean"), 1), fmt(g(a, "sd"), 2)), character(1)))
    rows[[length(rows)+1]] <- c("Median", vapply(ARMS, function(a) fmt(g(a, "median"), 1), character(1)))
    rows[[length(rows)+1]] <- c("Range", vapply(ARMS, function(a)
      sprintf("(%s, %s)", fmt(g(a, "min"), 1), fmt(g(a, "max"), 1)), character(1)))
  }
  for (v in names(CATV)) {
    rows[[length(rows)+1]] <- c(paste0("**", CATV[[v]], "**"), "", "", "")
    for (lv in unique(ard$variable_level[ard$variable == v & !is.na(ard$variable_level)]))
      rows[[length(rows)+1]] <- c(paste0("&nbsp;&nbsp;", lv), vapply(ARMS, function(a)
        sprintf("%s (%s%%)",
                fmt(get_stat(ard, group1 = a, variable = v, variable_level = lv, stat_name = "n"), 0),
                fmt(get_stat(ard, group1 = a, variable = v, variable_level = lv, stat_name = "pct"), 1)),
        character(1)))
  }
  write_display(c(L, md_table(H, rows), md_foot(spec, c(spec$notes,
    "No between-group test is presented: baseline testing in a randomized trial is discouraged (ICH E9), and at N=17 it would be meaningless."))), id)
}

# ============================================================ Hy's Law
gen_hyslaw <- function(id, spec, extra_note = character()) {
  pop <- gsub(" Population", "", spec$analysisSet$label)
  d <- read_adam(spec$dataSubset$dataset) %>% apply_cond(spec$dataSubset$condition) %>% set_arm()
  d <- d[!is.na(d$TRTP), , drop = FALSE]
  den <- pop_n(pop)
  ard <- NULL
  # Hy's Law is a SUBJECT property, not a record property — count subjects.
  for (a in ARMS) {
    da <- d[d$TRTP == a, , drop = FALSE]
    ns <- n_distinct(da$USUBJID[!is.na(da$CRIT1FL) & da$CRIT1FL == "Y"])
    ard <- rbind(ard,
      ard_row(a, "CRIT1", "ALT or AST >= 3xULN AND BILI >= 2xULN", "criterion", "n_subjects", ns),
      ard_row(a, "CRIT1", "ALT or AST >= 3xULN AND BILI >= 2xULN", "criterion", "pct_subjects",
              if (den[[a]] > 0) 100 * ns / den[[a]] else NA))
  }
  # component-level maxima so the reader can see how far from the threshold the data sits
  for (p in c("ALT", "AST", "BILI", "ALP")) {
    dp <- d[d$PARAMCD == p & !is.na(d$ANRHI) & d$ANRHI > 0, , drop = FALSE]
    if (!nrow(dp)) next
    dp$XULN <- dp$AVAL / dp$ANRHI
    for (a in ARMS) {
      x <- dp$XULN[dp$TRTP == a]; if (!length(x)) next
      ard <- rbind(ard,
        ard_row(a, paste0("XULN|", p), p, "criterion", "max_xuln", max(x, na.rm = TRUE)),
        ard_row(a, paste0("XULN|", p), p, "criterion", "n_subjects_ge_3x",
                n_distinct(dp$USUBJID[dp$TRTP == a & dp$XULN >= 3])))
    }
  }
  write_ard(ard, id)
  tot <- sum(vapply(ARMS, function(a) get_stat(ard, group1 = a, variable = "CRIT1", stat_name = "n_subjects"), numeric(1)), na.rm = TRUE)
  if (tot == 0) note_issue(id, "INFO", "0 subjects meet the Hy's Law criterion — a genuine negative finding, not a derivation gap")

  L <- md_head(spec, pop, extra_note)
  rows <- list(c("Subjects meeting Hy's Law criterion", vapply(ARMS, function(a)
    sprintf("%s (%s%%)", fmt(get_stat(ard, group1 = a, variable = "CRIT1", stat_name = "n_subjects"), 0),
            fmt(get_stat(ard, group1 = a, variable = "CRIT1", stat_name = "pct_subjects"), 1)), character(1))))
  rows2 <- lapply(c("ALT", "AST", "BILI", "ALP"), function(p) c(p, vapply(ARMS, function(a) {
    m <- get_stat(ard, group1 = a, variable = paste0("XULN|", p), stat_name = "max_xuln")
    n3 <- get_stat(ard, group1 = a, variable = paste0("XULN|", p), stat_name = "n_subjects_ge_3x")
    if (is.na(m)) "-" else sprintf("%s (%s subj >=3x)", fmt(m, 2), fmt(n3, 0)) }, character(1))))
  write_display(c(L, md_table(c("Criterion", hdr1(pop)[1:3]), rows), "",
    "#### Maximum observed value as a multiple of ULN (and subjects reaching 3xULN)", "",
    md_table(c("Analyte", hdr1(pop)[1:3]), rows2),
    md_foot(spec, c(spec$notes,
      "CRIT1 = ALT or AST >= 3xULN **and** total bilirubin >= 2xULN, evaluated per subject per analysis visit using the record-level `LBSTNRHI` as ULN.",
      "Counted at **subject** level: Hy's Law is a property of a subject, not of a record.",
      if (tot == 0) "**0 subjects met the criterion.** This is a genuine negative finding, not a missing derivation — the component maxima above show how far the observed values sit from the thresholds." else NULL))), id)
}
