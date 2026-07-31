# Name: 00_setup.R
# Description: Shared setup, IO helpers and the MANDATORY Rule-1 windowing engine.
# Driven by: outputs/tlf-plan/adam-spec.json
# ----------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(admiral); library(dplyr); library(tidyr); library(lubridate)
  library(stringr); library(rlang); library(haven); library(jsonlite)
  library(datasetjson)
})

ROOT     <- "/Users/vedha/Repo/FULL_WORKFLOW"
SDTM_DIR <- file.path(ROOT, "inputs", "sdtm")
ADAM_DIR <- file.path(ROOT, "outputs", "adam")
DATA_DIR <- file.path(ADAM_DIR, "data")
SPEC     <- jsonlite::read_json(file.path(ROOT, "outputs", "tlf-plan", "adam-spec.json"))

dir.create(DATA_DIR, showWarnings = FALSE, recursive = TRUE)

# ---- readers ---------------------------------------------------------------
read_sdtm <- function(domain) {
  f <- file.path(SDTM_DIR, paste0(tolower(domain), ".xpt"))
  if (!file.exists(f)) stop("SDTM domain not found: ", domain)
  d <- haven::read_xpt(f)                       # direct reader call
  as.data.frame(lapply(d, function(x) { attributes(x)$label <- NULL; x }),
                stringsAsFactors = FALSE)
}
read_adam <- function(name) {
  d <- read.csv(file.path(DATA_DIR, paste0(tolower(name), ".csv")),
                stringsAsFactors = FALSE, colClasses = c(USUBJID = "character"))
  # CSV round-trips dates as character; restore Date type on the *DT columns.
  for (v in grep("DT$", names(d), value = TRUE)) {
    if (is.character(d[[v]])) d[[v]] <- as.Date(d[[v]])
  }
  d
}

# ---- writer: CSV (primary, per user request) + Dataset-JSON ----------------
export_adam <- function(ds, name) {
  ds <- as.data.frame(ds, stringsAsFactors = FALSE)
  csv <- file.path(DATA_DIR, paste0(tolower(name), ".csv"))
  write.csv(ds, csv, row.names = FALSE, na = "")
  ok_json <- tryCatch({
    dj <- datasetjson::dataset_json(
      ds, item_oid = paste0("IG.", name), name = name,
      dataset_label = paste0(name, " analysis dataset"),
      columns = datasetjson::iso8601_to_dtc  # placeholder, replaced below
    ); TRUE
  }, error = function(e) FALSE)
  if (!ok_json) {
    # datasetjson's column-metadata contract varies by version; emit plain JSON
    # so the artifact still exists and is machine-readable.
    jsonlite::write_json(ds, file.path(DATA_DIR, paste0(tolower(name), ".json")),
                         dataframe = "rows", na = "null", auto_unbox = TRUE)
  }
  cat(sprintf("  exported %-10s %5d rows x %3d cols -> %s\n",
              name, nrow(ds), ncol(ds), basename(csv)))
  invisible(ds)
}

# ============================================================================
# MANDATORY RULE 1 — day-based analysis-visit windowing.
# NEVER assign AVISIT from a nominal VISITNUM lookup: that silently deletes
# unscheduled and early-termination records. Here the ED RETRIEVAL records fall
# at study days 169-173, i.e. squarely inside the Week-24 window — a nominal map
# would drop all six and empty the endpoint analysis.
#
# targets : named numeric vector  c("Baseline" = 1, "Week 24" = 169, ...)
#           Pass the target set the INSTRUMENT actually uses, not the full study
#           schedule — windowing onto visits an instrument never collects
#           misassigns records to empty bins.
# visitn  : named numeric vector of AVISITN values, same names as `targets`.
# ============================================================================
window_by_day <- function(df, day_var, targets, visitn) {
  stopifnot(all(names(targets) == names(visitn)))
  tv <- as.numeric(targets); nm <- names(targets)
  d  <- as.numeric(df[[day_var]])

  # boundaries at midpoints between adjacent targets
  idx <- vapply(d, function(x) {
    if (is.na(x)) return(NA_integer_)
    which.min(abs(tv - x))               # nearest target; ties -> earlier target
  }, integer(1))

  df$ADY     <- d
  df$AVISIT  <- ifelse(is.na(idx), NA_character_, nm[idx])
  df$AVISITN <- ifelse(is.na(idx), NA_real_, as.numeric(visitn[idx]))
  df$ATARGDY <- ifelse(is.na(idx), NA_real_, tv[idx])
  df
}

# One analysis record per subject x parameter x window: nearest target day,
# latest ADY breaks ties.
flag_nearest <- function(df, key = c("USUBJID", "PARAMCD", "AVISITN")) {
  df %>%
    group_by(across(all_of(key))) %>%
    mutate(.rk = rank(abs(ADY - ATARGDY) - ADY * 1e-6, ties.method = "first"),
           ANL01FL = if_else(.rk == 1, "Y", NA_character_),
           DTYPE   = NA_character_) %>%
    ungroup() %>% select(-.rk)
}

# ============================================================================
# MANDATORY RULE 2 — LOCF records at the endpoint visit.
# For every analysis-population subject with a baseline and >=1 post-baseline
# value but NO record in the endpoint window, carry the last observed
# post-baseline value forward as DTYPE='LOCF', ANL01FL='Y' at the endpoint.
# Exactly one ANL01FL='Y' record per subject per parameter per endpoint.
# ============================================================================
add_locf <- function(df, endpoint_n, endpoint_label, endpoint_day) {
  have <- df %>% filter(AVISITN == endpoint_n, ANL01FL == "Y") %>%
    distinct(USUBJID, PARAMCD)

  locf <- df %>%
    filter(ANL01FL == "Y", AVISITN > 0, !is.na(BASE), !is.na(AVAL)) %>%
    anti_join(have, by = c("USUBJID", "PARAMCD")) %>%
    group_by(USUBJID, PARAMCD) %>%
    slice_max(AVISITN, n = 1, with_ties = FALSE) %>%
    ungroup() %>%
    mutate(AVISIT = endpoint_label, AVISITN = endpoint_n, ATARGDY = endpoint_day,
           DTYPE = "LOCF", ANL01FL = "Y", CHG = AVAL - BASE,
           PCHG = if_else(BASE != 0, 100 * (AVAL - BASE) / BASE, NA_real_))

  cat(sprintf("  RULE 2 (LOCF): %d observed endpoint records, %d LOCF records created\n",
              nrow(have), nrow(locf)))
  bind_rows(df, locf)
}

# Baseline (ABLFL) = LAST non-missing record on or before first dose (ADY <= 1).
# `bl_cutoff` allows an instrument whose earliest assessment is pre-treatment
# screening (AVLT-REY has no BASELINE visit; its baseline is SCREENING 2).
derive_baseline <- function(df, bl_cutoff = 1) {
  bl <- df %>%
    filter(!is.na(AVAL), ADY <= bl_cutoff) %>%
    group_by(USUBJID, PARAMCD) %>%
    slice_max(ADY, n = 1, with_ties = FALSE) %>%
    ungroup() %>%
    transmute(USUBJID, PARAMCD, .blady = ADY, BASE = AVAL)

  df %>%
    left_join(bl, by = c("USUBJID", "PARAMCD")) %>%
    mutate(
      ABLFL = if_else(!is.na(.blady) & ADY == .blady, "Y", NA_character_),
      CHG   = if_else(!is.na(BASE) & ADY > bl_cutoff, AVAL - BASE, NA_real_),
      PCHG  = if_else(!is.na(BASE) & BASE != 0 & ADY > bl_cutoff,
                      100 * (AVAL - BASE) / BASE, NA_real_)
    ) %>%
    select(-.blady)
}

# Observed-cases flag: the primary record excluding LOCF (used by MMRM / descriptives).
add_anl02 <- function(df) {
  df %>% mutate(ANL02FL = if_else(!is.na(ANL01FL) & ANL01FL == "Y" &
                                    (is.na(DTYPE) | DTYPE == ""), "Y", NA_character_))
}

# Robust ISO-8601 -> Date. SDTM permits PARTIAL dates ("2012-11", "2012"); a
# bare as.Date() errors on them. Returns NA for anything short of a full date
# and reports how many were partial so the loss is visible, not silent.
safe_date <- function(x, label = "") {
  x  <- as.character(x); x[x == ""] <- NA_character_
  d10 <- substr(x, 1, 10)
  full <- !is.na(d10) & nchar(d10) == 10
  out <- as.Date(rep(NA_character_, length(x)))
  out[full] <- as.Date(d10[full])
  npart <- sum(!is.na(x) & !full)
  if (npart > 0 && nzchar(label))
    cat(sprintf("  NOTE: %s has %d partial/imprecise date(s) -> Date set to NA (study day retained)\n",
                label, npart))
  out
}

`%||%` <- function(a, b) if (is.null(a)) b else a
cat("00_setup.R loaded\n")
