# Name: 04_dq_gate.R
# Description: Data-quality (N) gate + metacore/metatools conformance + spec coverage.
# Implements the adam-spec.json data_quality_gate assertions NG-1 .. NG-8.
# Exits non-zero on any `error`-severity shortfall so the pipeline cannot proceed
# on corrupted denominators.
# ----------------------------------------------------------------------------
source("00_setup.R")
suppressPackageStartupMessages({ library(metacore); library(metatools); library(tibble) })

RES <- list(); FAIL <- 0L
rec <- function(id, label, actual, expected, sev = "error", note = "") {
  ok <- isTRUE(all.equal(actual, expected))
  if (!ok && sev == "error") FAIL <<- FAIL + 1L
  status <- if (ok) "PASS" else if (sev == "error") "**FAIL**" else "WARN"
  cat(sprintf("  [%-8s] %-6s %-52s actual=%-6s expected=%-6s\n",
              status, id, label, paste(actual, collapse=","), paste(expected, collapse=",")))
  RES[[length(RES) + 1]] <<- data.frame(id, label, actual = paste(actual, collapse=", "),
                                        expected = paste(expected, collapse=", "),
                                        severity = sev, status = gsub("\\*", "", status),
                                        note = note, stringsAsFactors = FALSE)
  invisible(ok)
}

adsl <- read_adam("ADSL")
cat("\n================ DATA-QUALITY GATE ================\n")

# ---- NG-1 / NG-2 / NG-3: ADSL population accounting -------------------------
rec("NG-1", "ADSL total records", nrow(adsl), 18L, "error",
    "18 DM records = 17 randomized + 1 screen failure (CDISC015).")
rec("NG-1b", "ADSL ITTFL='Y'", sum(adsl$ITTFL == "Y"), 17L, "error",
    "Screen failure correctly excluded from ITT.")
arm_n <- adsl %>% filter(ITTFL == "Y") %>% count(TRT01P) %>% arrange(TRT01P)
rec("NG-2", "ITT N by arm (Placebo/High/Low)", arm_n$n, c(5L, 7L, 5L), "error")
rec("NG-3", "ADSL SAFFL='Y' == ITTFL='Y'", sum(adsl$SAFFL == "Y"), sum(adsl$ITTFL == "Y"),
    "warning", "All randomized subjects were dosed.")

# ---- NG-6: SITEGR1 (MANDATORY RULE 3, randomized counts) --------------------
ng6 <- n_distinct(adsl$SITEGR1[adsl$ITTFL == "Y"])
rec("NG-6", "distinct SITEGR1 groups (randomized)", ng6, 1L, "warning",
    paste("Rule 3 applied on randomized counts. 17 subjects over 6 sites and 3 arms means no",
          "site reaches 3 randomized subjects in every arm, so all pool to 900. SITEGR1 is",
          "single-level and rank-deficient as an ANCOVA covariate -> the generator must refit",
          "without it. This is the rule working, not a defect."))

# ---- NG-4 / NG-5 / NG-7: per-BDS derivation correctness ---------------------
# NG-4 is the direct test of MANDATORY RULE 2: the endpoint analysis N must equal
# the number of subjects with a baseline and >=1 post-baseline record. A value
# equal to the raw observed Week-24 count means LOCF did not run.
bds <- list(
  ADQSPHQ  = list(param = "PHQTOT",  src = "QSPH", key = "PHQ0111"),
  ADQSSWL  = list(param = "SWLSTOT", src = "QSSL", key = "SWLS0101"),
  ADFTAVLT = list(param = "AVLATOT", src = "FT",   key = "AVL0216"),
  ADRSHAMD = list(param = "HAMD118", src = "RS",   key = "HAMD118")
)
src_day <- function(dom, testcd) {
  d <- read_sdtm(dom)
  tc <- grep("TESTCD$", names(d), value = TRUE)[1]
  dy <- grep("DY$", names(d), value = TRUE)[1]
  rs <- grep("STRESN$", names(d), value = TRUE)[1]
  d[d[[tc]] == testcd & !is.na(d[[rs]]), c("USUBJID", dy)] %>%
    setNames(c("USUBJID", "DY"))
}
cat("\n  -- per-dataset endpoint N (NG-4: direct test of MANDATORY RULE 2) --\n")
for (nm in names(bds)) {
  b  <- bds[[nm]]; ds <- read_adam(nm)
  sd_ <- src_day(b$src, b$key)
  elig <- sd_ %>% group_by(USUBJID) %>%
    summarise(bl = any(DY <= 1, na.rm = TRUE), pb = any(DY > 1, na.rm = TRUE), .groups = "drop") %>%
    filter(bl, pb) %>% nrow()
  eligid <- sd_ %>% group_by(USUBJID) %>%
    summarise(bl = any(DY <= 1, na.rm = TRUE), pb = any(DY > 1, na.rm = TRUE), .groups = "drop") %>%
    filter(bl, pb) %>% pull(USUBJID)
  epid <- ds %>% filter(PARAMCD == b$param, AVISITN == 24, ANL01FL == "Y") %>%
    distinct(USUBJID) %>% pull(USUBJID)
  ep  <- length(epid)
  obs <- ds %>% filter(PARAMCD == b$param, AVISITN == 24, ANL01FL == "Y",
                       is.na(DTYPE) | DTYPE == "") %>% distinct(USUBJID) %>% nrow()
  nobase <- ds %>% filter(PARAMCD == b$param, AVISITN == 24, ANL01FL == "Y",
                          is.na(BASE)) %>% distinct(USUBJID) %>% nrow()
  # THE ASSERTION: no subject with baseline + >=1 post-baseline may be MISSING
  # from the endpoint analysis. A shortfall means windowing or LOCF dropped them.
  # Endpoint records held by subjects with NO baseline are legitimate (they are
  # observed records; their CHG is simply missing) and are NOT a defect.
  dropped <- setdiff(eligid, epid)
  rec(paste0("NG-4/", nm), paste0(b$param, " eligible subjects dropped from endpoint"),
      length(dropped), 0L, "error",
      sprintf(paste("Shortfall test of MANDATORY RULE 2. endpoint N=%d (observed %d, LOCF %d);",
                    "eligible (baseline + post-baseline) = %d; %d endpoint record(s) have no",
                    "baseline so contribute no CHG.%s"),
              ep, obs, ep - obs, length(eligid), nobase,
              if (length(dropped)) paste(" DROPPED:", paste(dropped, collapse = ", ")) else ""))
  # NG-7: exactly one primary record per subject per parameter at the endpoint
  dup <- ds %>% filter(AVISITN == 24, ANL01FL == "Y") %>% count(USUBJID, PARAMCD) %>% filter(n > 1)
  rec(paste0("NG-7/", nm), "duplicate ANL01FL primary records at endpoint", nrow(dup), 0L, "error")
}

# NG-5: no source record lost to windowing (MANDATORY RULE 1).
cat("\n  -- NG-5: record retention through windowing (MANDATORY RULE 1) --\n")
retention <- list(
  list(ad = "ADLB", dom = "LB", filt = function(d) !is.na(d$LBSTRESN) &
         !d$LBTESTCD %in% c("ANISO","COLOR","KETONES","MACROCY","POIKILO","UROBIL")),
  list(ad = "ADVS", dom = "VS", filt = function(d) !is.na(d$VSSTRESN))
)
for (r in retention) {
  s <- read_sdtm(r$dom); nsrc <- sum(r$filt(s))
  a <- read_adam(r$ad); nobs <- sum(is.na(a$DTYPE) | a$DTYPE == "")
  rec(paste0("NG-5/", r$ad), "observed analysis records vs source records", nobs, nsrc,
      "error", "Any shortfall means windowing dropped source records.")
}
# ED / unscheduled survival — the specific failure mode Rule 1 guards against
ed_check <- read_adam("ADQSPHQ") %>% filter(SRCVISIT == "EARLY DISCONTINUATION RETRIEVAL") %>%
  distinct(USUBJID) %>% nrow()
rec("NG-5b", "PHQ-9 early-discontinuation records retained", ed_check, 6L, "error",
    "These 6 records fall at study days 169-173 and window to Week 24. A nominal-VISITNUM map would drop them.")
unsch <- read_adam("ADLB") %>% filter(grepl("UNSCHEDULED", SRCVISIT)) %>% nrow()
rec("NG-5c", "ADLB unscheduled-visit records retained", unsch > 0, TRUE, "error")

# ---- NG-8: AE / death reconciliation ----------------------------------------
adae <- read_adam("ADAE")
rec("NG-8", "distinct subjects AEOUT=FATAL vs ADSL DTHFL=Y",
    n_distinct(adae$USUBJID[adae$AEOUT == "FATAL"]), sum(adsl$DTHFL == "Y", na.rm = TRUE),
    "warning", "Source-data consistency check, not a derivation check.")

# ============================================================================
# CONFORMANCE — spec variables present + metacore/metatools where constructible
# ============================================================================
cat("\n================ SPEC COVERAGE / CONFORMANCE ================\n")
cov <- list()
for (d in SPEC$datasets) {
  nm <- d$name
  f <- file.path(DATA_DIR, paste0(tolower(nm), ".csv"))
  if (!file.exists(f)) {
    cov[[length(cov)+1]] <- data.frame(dataset = nm, rows = NA, params_ok = "-",
      vars_present = "0/0", missing = "DATASET NOT DERIVED", status = "FAIL")
    next
  }
  ds <- read_adam(nm)
  want <- vapply(d$variables, function(v) v$name, character(1))
  want <- want[!grepl("^<", want)]                      # skip templated names
  have <- names(ds)
  miss <- setdiff(want, have)
  pcds <- vapply(d$parameters, function(p) p$paramcd, character(1))
  pcds <- pcds[!grepl("^<|/", pcds)]
  pmiss <- if (length(pcds) && "PARAMCD" %in% have) setdiff(pcds, unique(ds$PARAMCD)) else character(0)
  cov[[length(cov)+1]] <- data.frame(
    dataset = nm, rows = nrow(ds),
    params_ok = if (!length(pcds)) "n/a" else sprintf("%d/%d", length(pcds) - length(pmiss), length(pcds)),
    vars_present = sprintf("%d/%d", length(want) - length(miss), length(want)),
    missing = if (length(miss) || length(pmiss))
      paste(c(miss, paste0("PARAMCD:", pmiss)), collapse = ", ") else "",
    status = if (!length(miss) && !length(pmiss)) "OK" else "GAP",
    stringsAsFactors = FALSE)
}
COV <- bind_rows(cov); print(COV, right = FALSE)

# metacore / metatools — attempt a real conformance run on ADSL
mc_note <- tryCatch({
  vs_ <- SPEC$datasets[[1]]$variables
  var_spec <- data.frame(
    variable = vapply(vs_, function(v) v$name, character(1)),
    label    = substr(vapply(vs_, function(v) v$role, character(1)), 1, 40),
    type     = "text", length = 200, common = NA, format = NA_character_,
    stringsAsFactors = FALSE) %>% distinct(variable, .keep_all = TRUE)
  ds_spec  <- data.frame(dataset = "ADSL", structure = "one record per subject",
                         label = "Subject Level Analysis Dataset", stringsAsFactors = FALSE)
  ds_vars  <- data.frame(dataset = "ADSL", variable = var_spec$variable,
                         keep = TRUE, key_seq = NA_integer_, order = seq_len(nrow(var_spec)),
                         core = "Req", supp_flag = FALSE, stringsAsFactors = FALSE)
  val_spec <- data.frame(dataset = "ADSL", variable = var_spec$variable,
                         where = NA_character_, type = "text", sig_dig = NA_integer_,
                         code_id = NA_character_, origin = "Derived",
                         derivation_id = paste0("DRV.", var_spec$variable),
                         stringsAsFactors = FALSE)
  derivs  <- data.frame(derivation_id = val_spec$derivation_id,
                        derivation = "see adam-spec.json variables[].role/source",
                        stringsAsFactors = FALSE)
  codelist <- tibble::tibble(code_id = character(), name = character(),
                             type = character(), codes = list())
  supp <- tibble::tibble(dataset = character(), variable = character(),
                         idvar = character(), qeval = character())
  mc <- suppressWarnings(metacore::metacore(
    ds_spec = ds_spec, ds_vars = ds_vars, var_spec = var_spec,
    value_spec = val_spec, derivations = derivs, codelist = codelist,
    supp = supp, quiet = TRUE))
  mc1 <- metacore::select_dataset(mc, "ADSL")
  chk <- try(metatools::check_variables(read_adam("ADSL"), mc1), silent = TRUE)
  if (inherits(chk, "try-error")) paste("metatools::check_variables reported:",
                                        trimws(gsub("\\s+", " ", as.character(chk))))
  else "metatools::check_variables(ADSL): all spec variables present, no extras flagged."
}, error = function(e) paste("metacore object could not be constructed:", conditionMessage(e)))
cat("\nmetacore/metatools:", mc_note, "\n")

# ---- write reports -----------------------------------------------------------
DQ <- bind_rows(RES)
md <- c("# Data-Quality Gate — CDISCPILOT01 ADaM", "",
  sprintf("Run: spec-driven from `outputs/tlf-plan/adam-spec.json`. Error-severity failures: **%d**.", FAIL), "",
  "The gate asserts **derivation correctness** (did we lose records? did LOCF run?), not",
  "statistical adequacy. With 17 randomized subjects this study cannot meet a conventional",
  "N threshold and every inferential result downstream is illustrative only.", "",
  "| ID | Check | Actual | Expected | Severity | Status |",
  "|---|---|---|---|---|---|",
  sprintf("| %s | %s | %s | %s | %s | %s |", DQ$id, DQ$label, DQ$actual, DQ$expected, DQ$severity, DQ$status),
  "", "## Notes", "",
  sprintf("- **%s** — %s", DQ$id[nzchar(DQ$note)], DQ$note[nzchar(DQ$note)]))
writeLines(md, file.path(ADAM_DIR, "data-quality.md"))

cm <- c("# ADaM Spec Coverage — CDISCPILOT01", "",
  "Every dataset, parameter and variable demanded by `adam-spec.json`, checked against the derived data.", "",
  "| Spec dataset | Rows | Parameters | Variables present | Missing | Status |",
  "|---|---|---|---|---|---|",
  sprintf("| %s | %s | %s | %s | %s | %s |", COV$dataset, COV$rows, COV$params_ok,
          COV$vars_present, ifelse(COV$missing == "", "—", COV$missing), COV$status))
writeLines(cm, file.path(ADAM_DIR, "spec-coverage.md"))

conf <- c("# Conformance — CDISCPILOT01 ADaM", "",
  "## metacore / metatools", "", paste0("- ", mc_note), "",
  "## Spec-variable conformance", "",
  "See `spec-coverage.md` for the per-dataset variable and parameter check. Every dataset",
  "was checked directly against the `variables[]` and `parameters[]` arrays of `adam-spec.json`.", "",
  sprintf("- Datasets checked: %d", nrow(COV)),
  sprintf("- Datasets fully conformant: %d", sum(COV$status == "OK")),
  sprintf("- Datasets with gaps: %d", sum(COV$status == "GAP")))
writeLines(conf, file.path(ADAM_DIR, "conformance.md"))

cat(sprintf("\n================ GATE RESULT: %s (%d error-severity failure%s) ================\n",
            if (FAIL == 0) "PASS" else "FAIL", FAIL, if (FAIL == 1) "" else "s"))
if (FAIL > 0) quit(status = 1)
