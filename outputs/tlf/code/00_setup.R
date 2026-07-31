# Name: 00_setup.R
# Description: Shared helpers for TLF generation. ARD-first: every statistic is
#              computed into a tidy ARD and persisted; the display renders the
#              ARD. Nothing is computed inside a renderer; no value is hand-entered.
# ----------------------------------------------------------------------------
suppressPackageStartupMessages({
  library(dplyr); library(tidyr); library(jsonlite); library(cards); library(cardx)
  library(emmeans); library(survival); library(ggsurvfit); library(ggplot2)
  library(gtsummary); library(mmrm); library(MASS, warn.conflicts = FALSE)
})
select <- dplyr::select; filter <- dplyr::filter

ROOT     <- "/Users/vedha/Repo/FULL_WORKFLOW"
ADAM_DIR <- file.path(ROOT, "outputs", "adam", "data")
TLF_DIR  <- file.path(ROOT, "outputs", "tlf")
SPECS    <- jsonlite::fromJSON(file.path(ROOT, "outputs", "tlf-plan", "analysis-spec.json"),
                               simplifyVector = FALSE)
names(SPECS) <- vapply(SPECS, function(s) s$id, character(1))

# ---- GOLDEN RULE 2: SAS rounding (half away from zero) — DISPLAY ONLY --------
sas_round <- function(x, d = 0) { z <- abs(x) * 10^d; z <- floor(z + 0.5); sign(x) * z / 10^d }
fmt <- function(x, d) ifelse(is.na(x), "-", formatC(sas_round(x, d), format = "f", digits = d))
fmtp <- function(p) ifelse(is.na(p), "-", ifelse(p < 0.001, "<0.001", formatC(sas_round(p, 3), format = "f", digits = 3)))

read_adam <- function(name) read.csv(file.path(ADAM_DIR, paste0(tolower(name), ".csv")),
                                     stringsAsFactors = FALSE)

ADSL <- read_adam("ADSL")
ARMS <- c("Placebo", "Zanomaline Low Dose (54 mg)", "Zanomaline High Dose (81 mg)")
ARMS_SHORT <- c("Placebo", "Zanomaline Low\n(54 mg)", "Zanomaline High\n(81 mg)")

# ---- Population N ALWAYS from ADSL (one row per subject), never from a BDS ---
pop_flag <- function(pop) switch(pop,
  "Efficacy" = "EFFFL", "Safety" = "SAFFL", "Intent-to-Treat" = "ITTFL",
  "Completers" = "COMPLFL", "All Subjects" = NA_character_, NA_character_)
pop_subjects <- function(pop) {
  f <- pop_flag(pop)
  d <- if (is.na(f)) ADSL else ADSL[ADSL[[f]] == "Y", , drop = FALSE]
  d[!is.na(d$TRT01P), , drop = FALSE]
}
pop_n <- function(pop) {
  d <- pop_subjects(pop)
  n <- vapply(ARMS, function(a) sum(d$TRT01P == a), integer(1))
  c(n, Total = sum(n))
}
hdr <- function(pop) {
  n <- pop_n(pop)
  sprintf("%s\n(N=%d)", c(ARMS, "Total"), n)
}

set_arm <- function(d, var = "TRTP") {
  d[[var]] <- factor(d[[var]], levels = ARMS)
  d
}

# ---- ARD assembly / persistence ---------------------------------------------
ard_row <- function(group1 = NA, variable = NA, variable_level = NA, context = NA,
                    stat_name = NA, stat = NA) {
  data.frame(group1 = as.character(group1), variable = as.character(variable),
             variable_level = as.character(variable_level), context = as.character(context),
             stat_name = as.character(stat_name), stat = as.numeric(stat),
             stringsAsFactors = FALSE)
}
flatten_ard <- function(a, context) {
  # cards returns group1_level / stat as LIST-COLUMNS holding factors — coerce.
  data.frame(
    group1        = as.character(unlist(lapply(a$group1_level, function(x) if (is.null(x)) NA else as.character(x)))),
    variable      = as.character(a$variable),
    variable_level = as.character(unlist(lapply(a$variable_level, function(x) if (is.null(x)) NA else as.character(x)))),
    context       = context,
    stat_name     = as.character(a$stat_name),
    stat          = suppressWarnings(as.numeric(unlist(lapply(a$stat, function(x) if (is.null(x)) NA else x[1])))),
    stringsAsFactors = FALSE)
}
write_ard <- function(ard, id) {
  d <- file.path(TLF_DIR, id); dir.create(d, showWarnings = FALSE, recursive = TRUE)
  ard <- ard[!is.na(ard$stat_name), , drop = FALSE]
  write.csv(ard, file.path(d, "ard.csv"), row.names = FALSE, na = "")
  jsonlite::write_json(ard, file.path(d, "ard.json"), dataframe = "rows",
                       na = "null", auto_unbox = TRUE)
  cat(sprintf("    ARD: %d statistics -> %s/ard.csv\n", nrow(ard), id))
  invisible(ard)
}
write_display <- function(lines, id) {
  d <- file.path(TLF_DIR, id); dir.create(d, showWarnings = FALSE, recursive = TRUE)
  writeLines(lines, file.path(d, paste0(id, ".generated.md")))
  cat(sprintf("    display -> %s/%s.generated.md\n", id, id))
}
get_stat <- function(ard, ...) {
  f <- list(...); x <- ard
  for (nm in names(f)) x <- x[!is.na(x[[nm]]) & x[[nm]] == f[[nm]], , drop = FALSE]
  if (nrow(x) == 0) NA_real_ else x$stat[1]
}

# ---- Display scaffolding -----------------------------------------------------
md_head <- function(spec, pop, extra = character()) {
  n <- pop_n(pop)
  c(sprintf("# %s  %s", sub("^AN-", "", spec$id), spec$title), "",
    sprintf("**Protocol:** %s  |  **Population:** %s  |  **Reason:** %s",
            spec$protocol, spec$analysisSet$label, spec$reason), "",
    sprintf("**Analysis set:** `%s`  —  Placebo N=%d, Zanomaline Low N=%d, Zanomaline High N=%d, Total N=%d",
            spec$analysisSet$condition, n[1], n[2], n[3], n[4]), "",
    if (length(extra)) c(extra, "") else NULL)
}
FOOT_N <- paste("**N-GATE WARNING.** This study randomized 17 subjects (Placebo 5 / Zanomaline Low 5 /",
                "Zanomaline High 7). Every inferential statistic in this display is **illustrative only**",
                "and must not be interpreted as evidence of effect or of absence of effect.")
md_foot <- function(spec, notes = character()) {
  c("", "---", "", "### Notes", "",
    paste0("- ", c(notes, "All values computed from ADaM via the persisted ARD (`ard.csv`); no value is hand-entered.",
                   "Rounding: SAS convention (half away from zero), applied at display time only.")),
    "", paste0("> ", FOOT_N))
}
md_table <- function(header, rows) {
  c(paste0("| ", paste(header, collapse = " | "), " |"),
    paste0("|", paste(rep("---", length(header)), collapse = "|"), "|"),
    vapply(rows, function(r) paste0("| ", paste(r, collapse = " | "), " |"), character(1)))
}
hdr1 <- function(pop) gsub("\n", " ", hdr(pop))

ISSUES <- new.env(parent = emptyenv()); ISSUES$rows <- list()
note_issue <- function(id, severity, msg) {
  ISSUES$rows[[length(ISSUES$rows) + 1]] <- data.frame(id, severity, msg, stringsAsFactors = FALSE)
  cat(sprintf("    [%s] %s\n", severity, msg))
}
cat("tlf 00_setup.R loaded — ADSL N =", nrow(ADSL),
    "| ITT", sum(ADSL$ITTFL == "Y"), "| SAF", sum(ADSL$SAFFL == "Y"),
    "| EFF", sum(ADSL$EFFFL == "Y"), "\n")
