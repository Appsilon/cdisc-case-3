# Fixed, deterministic aggregates over the staged ADaM for the accuracy gates (accuracy.py builds the requests).
#   Rscript --vanilla recompute.R <plan.json> <result.json>
# plan = {adamDir, requests: [{key, dataset, population, where, variable, level, tabulate}]}; a condition is
# {variable, comparator: EQ NE GT GE LT LE IN NOTIN ISNULL NOTNULL, values}. population is evaluated on ADSL; where on the
# analysis dataset, a variable it lacks is taken from ADSL by USUBJID.
arguments <- commandArgs(TRUE)
plan <- jsonlite::fromJSON(arguments[1], simplifyVector = FALSE)
cache <- new.env()

dataset <- function(name) {
  key <- toupper(name)
  if (is.null(cache[[key]])) {
    data <- as.data.frame(haven::zap_labels(haven::read_xpt(file.path(plan$adamDir, paste0(tolower(name), ".xpt")))))
    for (column in names(data)[vapply(data, is.character, logical(1))]) {
      invalid <- !is.na(data[[column]]) & !validUTF8(data[[column]])
      data[[column]][invalid] <- iconv(data[[column]][invalid], "latin1", "UTF-8")
    }
    cache[[key]] <- data
  }
  cache[[key]]
}

column_of <- function(records, adsl, variable) {
  if (variable %in% names(records)) return(records[[variable]])
  if (variable %in% names(adsl)) return(adsl[[variable]][match(records$USUBJID, adsl$USUBJID)])
  stop(paste0("neither the analysis dataset nor ADSL has ", variable))
}

is_missing <- function(values) {
  if (is.character(values)) is.na(values) | trimws(values) == "" else is.na(values)
}

holds <- function(values, condition) {
  wanted <- unlist(condition$values)
  missing <- is_missing(values)
  comparable <- if (is.numeric(values)) values else trimws(as.character(values))
  targets <- if (is.numeric(values)) suppressWarnings(as.numeric(wanted)) else trimws(as.character(wanted))
  ordering <- condition$comparator %in% c("GT", "GE", "LT", "LE")
  if (ordering && !is.numeric(values) && length(wanted) > 0 && !anyNA(suppressWarnings(as.numeric(wanted)))) {
    comparable <- suppressWarnings(as.numeric(comparable))
    targets <- as.numeric(wanted)
    missing <- missing | is.na(comparable)
  }
  wants_missing <- length(wanted) > 0 && any(trimws(as.character(wanted)) == "")
  equal <- (!missing & comparable %in% targets[!is.na(targets)]) | (missing & wants_missing)
  result <- switch(condition$comparator,
    EQ = equal, IN = equal, NE = !equal, NOTIN = !equal,
    GT = !missing & comparable > targets[1], GE = !missing & comparable >= targets[1],
    LT = !missing & comparable < targets[1], LE = !missing & comparable <= targets[1],
    ISNULL = missing, NOTNULL = !missing,
    stop(paste0("unsupported comparator ", condition$comparator)))
  !is.na(result) & result
}

all_hold <- function(records, adsl, conditions) {
  keep <- rep(TRUE, nrow(records))
  for (condition in conditions) keep <- keep & holds(column_of(records, adsl, condition$variable), condition)
  keep
}

subject_count <- function(ids) length(unique(ids))

evaluate <- function(request) {
  adsl <- dataset("ADSL")
  subjects <- adsl$USUBJID[all_hold(adsl, adsl, request$population)]
  records <- dataset(request$dataset)
  records <- records[records$USUBJID %in% subjects, , drop = FALSE]
  records <- records[all_hold(records, adsl, request$where), , drop = FALSE]
  result <- list(subjects = subject_count(records$USUBJID), records = nrow(records))
  if (!is.null(request$tabulate)) {
    levels <- trimws(as.character(column_of(records, adsl, request$tabulate)))
    levels[is.na(levels)] <- ""
    counts <- tapply(records$USUBJID, levels, subject_count)
    result$counts <- if (length(counts) == 0) structure(list(), names = character(0)) else as.list(counts)
  }
  if (!is.null(request$variable)) {
    values <- column_of(records, adsl, request$variable)
    present <- !is_missing(values)
    result$nonmissingRecords <- sum(present)
    result$nonmissingSubjects <- subject_count(records$USUBJID[present])
    if (!is.null(request$level)) {
      hit <- holds(values, list(comparator = "EQ", values = list(request$level)))
      result$levelRecords <- sum(hit)
      result$levelSubjects <- subject_count(records$USUBJID[hit])
    }
    if (is.numeric(values) && sum(present) > 0) {
      numbers <- values[present]
      result$mean <- mean(numbers)
      result$sd <- if (length(numbers) > 1) sd(numbers) else NA
      result$median <- median(numbers)
      result$min <- min(numbers)
      result$max <- max(numbers)
    }
  }
  result
}

results <- list()
for (request in plan$requests) {
  results[[request$key]] <- tryCatch(evaluate(request), error = function(problem) list(error = conditionMessage(problem)))
}
jsonlite::write_json(results, arguments[2], auto_unbox = TRUE, digits = NA, na = "null")
