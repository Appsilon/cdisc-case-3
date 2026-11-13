# Run one ADaM program in this (fresh) R session and export what it saved.
#
# Usage: Rscript --vanilla run_program.R <program.R> <DATASET> <xpt-dir> <manifest.json>
# Env:   SDTM_DIR (staged SDTM), ADAM_DIR (where programs save and read <dataset>.rds)
#
# Every warning and error is printed as a "WARNING: " / "ERROR: " line so the
# driver can enforce a clean log. The saved data frame is written as SAS V5
# transport (<dataset>.xpt) and described in the manifest (column name, type,
# label, length, display format) that check-lineage and generate-define read.

args <- commandArgs(trailingOnly = TRUE)
program <- normalizePath(args[[1]])
dataset <- toupper(args[[2]])
xpt_dir <- args[[3]]
manifest_path <- args[[4]]

warnings_seen <- 0L
fail <- function(text) {
  message("ERROR: ", text)
  quit(save = "no", status = 1)
}

withCallingHandlers(
  tryCatch(
    sys.source(program, envir = new.env(parent = globalenv()), chdir = TRUE),
    error = function(condition) fail(conditionMessage(condition))
  ),
  warning = function(condition) {
    text <- conditionMessage(condition)
    # About the installation, not the program: logged, never fails the run.
    if (grepl("was built under R version", text, fixed = TRUE)) {
      message("NOTE: ", text)
    } else {
      warnings_seen <<- warnings_seen + 1L
      message("WARNING: ", text)
    }
    invokeRestart("muffleWarning")
  }
)

rds_path <- file.path(Sys.getenv("ADAM_DIR"), paste0(tolower(dataset), ".rds"))
if (!file.exists(rds_path)) fail(paste0(basename(program), " did not save ", rds_path))
data <- readRDS(rds_path)
if (!is.data.frame(data)) fail(paste0(basename(rds_path), " is not a data frame"))
if (nrow(data) == 0) fail(paste0(dataset, " has no rows"))

problems <- character()
columns <- list()
for (name in names(data)) {
  column <- data[[name]]
  label <- attr(column, "label", exact = TRUE)
  label <- if (is.null(label)) "" else as.character(label)
  if (is.factor(column)) {
    column <- as.character(column)
  }
  if (inherits(column, "POSIXct")) {
    type <- "datetime"; display <- "DATETIME20."
  } else if (inherits(column, "Date")) {
    type <- "date"; display <- "DATE9."
  } else if (inherits(column, "difftime")) {
    column <- as.numeric(column); type <- "float"; display <- ""
  } else if (is.character(column)) {
    type <- "text"; display <- ""
  } else if (is.numeric(column)) {
    whole <- all(is.na(column) | column == round(column))
    type <- if (whole) "integer" else "float"; display <- ""
  } else {
    problems <- c(problems, sprintf("%s.%s: type %s cannot go to SAS V5 (use character or numeric)", dataset, name, class(column)[1]))
    next
  }
  length <- if (type == "text") max(c(1L, nchar(column[!is.na(column)], type = "bytes"))) else 8L
  # Decimal places actually present, for def:SignificantDigits on float items.
  digits <- 0L
  if (type == "float") {
    decimals <- nchar(sub("^[^.]*[.]?", "", format(column[!is.na(column)], scientific = FALSE, trim = TRUE, digits = 15)))
    digits <- min(max(c(0L, decimals)), 15L)
  }
  if (!grepl("^[A-Z][A-Z0-9_]{0,7}$", name)) problems <- c(problems, sprintf("%s.%s: name must be upper case, at most 8 characters", dataset, name))
  if (label == "") problems <- c(problems, sprintf("%s.%s: no label (set attr(x, \"label\"))", dataset, name))
  if (nchar(label) > 40) problems <- c(problems, sprintf("%s.%s: label longer than 40 characters", dataset, name))
  if (type == "text" && length > 200) problems <- c(problems, sprintf("%s.%s: values longer than 200 bytes", dataset, name))
  attr(column, "label") <- if (label == "") NULL else label
  if (display != "") attr(column, "format.sas") <- sub("\\.$", "", display)
  data[[name]] <- column
  columns[[length(columns) + 1]] <- list(name = name, type = type, label = label, length = length, format = display, digits = digits)
}

xpt_path <- file.path(xpt_dir, paste0(tolower(dataset), ".xpt"))
if (length(problems) == 0) {
  haven::write_xpt(data, xpt_path, version = 5, name = dataset)
}
jsonlite::write_json(
  list(dataset = dataset, rows = nrow(data), columns = columns, problems = problems, warnings = warnings_seen,
       # I(): auto_unbox would write a single PARAMCD as a string, not a one-item list.
       paramcd = I(if ("PARAMCD" %in% names(data)) sort(unique(as.character(data$PARAMCD))) else character())),
  manifest_path, auto_unbox = TRUE, pretty = TRUE
)
for (problem in problems) message("ERROR: ", problem)
if (length(problems) > 0) quit(save = "no", status = 1)
