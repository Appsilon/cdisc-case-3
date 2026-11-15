# Profile every column of every ADaM dataset for the traceability explorer.
#   Rscript profile_adam.R <output.json> <dataset.xpt> ...
# Per column: label, kind, n / missing / distinct, the top levels (categorical) or
# a numeric / date summary, the same by treatment arm, and a few example records.
arguments <- commandArgs(TRUE)
output <- arguments[1]
paths <- arguments[-1]
MAX_LEVELS <- 12
ARM_CANDIDATES <- c("TRTP", "TRT01P", "TRTA", "TRT01A", "ARM")
KEY_CANDIDATES <- c("USUBJID", "PARAMCD", "AVISIT")

blank <- function(values) is.na(values) | (is.character(values) & trimws(values) == "")
round_value <- function(value) if (is.numeric(value)) signif(value, 6) else value

summary_of <- function(values) {
  values <- values[!blank(values)]
  if (length(values) == 0) return(NULL)
  if (inherits(values, "Date")) return(list(min = format(min(values)), max = format(max(values))))
  numbers <- as.numeric(values)
  list(min = round_value(min(numbers)), max = round_value(max(numbers)), mean = round_value(mean(numbers)),
       median = round_value(stats::median(numbers)), sd = if (length(numbers) > 1) round_value(stats::sd(numbers)) else NULL)
}

profile_column <- function(values, arms, keys, data) {
  missing <- blank(values)
  present <- values[!missing]
  distinct <- length(unique(present))
  categorical <- is.character(values) || (distinct <= MAX_LEVELS && !inherits(values, "Date"))
  kind <- if (inherits(values, "Date")) "date" else if (is.character(values)) "char" else "num"
  profile <- list(kind = kind, n = length(values), nmiss = sum(missing), nuniq = distinct)
  if (categorical) {
    counts <- sort(table(as.character(present)), decreasing = TRUE)
    top <- head(counts, MAX_LEVELS)
    profile$levels <- lapply(names(top), function(level) list(v = level, n = as.integer(top[[level]])))
    profile$levelsMore <- max(0, length(counts) - MAX_LEVELS)
  } else {
    profile$summary <- summary_of(values)
  }
  if (!is.null(arms)) {
    arm_levels <- sort(unique(arms[!blank(arms)]))
    by_arm <- list(arms = I(arm_levels))
    if (categorical && distinct <= MAX_LEVELS) {
      by_arm$kind <- "cat"
      by_arm$rows <- lapply(names(sort(table(as.character(present)), decreasing = TRUE)), function(level) {
        list(v = level, cells = I(vapply(arm_levels, function(arm) sum(!missing & as.character(values) == level & arms %in% arm), 0)))
      })
    } else if (!categorical) {
      by_arm$kind <- "num"
      by_arm$cells <- lapply(arm_levels, function(arm) summary_of(values[arms %in% arm]))
    }
    if (!is.null(by_arm$kind)) profile$byArm <- by_arm
  }
  shown <- which(!missing)
  shown <- shown[!duplicated(as.character(values[shown]))]
  profile$examples <- lapply(head(shown, 6), function(row) {
    list(k = I(vapply(keys, function(key) as.character(data[[key]][row]), "")), v = as.character(values[row]))
  })
  profile
}

profiles <- list()
for (path in paths) {
  dataset <- toupper(tools::file_path_sans_ext(basename(path)))
  profiles[[dataset]] <- tryCatch({
    data <- haven::read_xpt(path)
    arm_variable <- intersect(ARM_CANDIDATES, names(data))[1]
    arms <- if (is.na(arm_variable)) NULL else as.character(data[[arm_variable]])
    keys <- intersect(KEY_CANDIDATES, names(data))
    columns <- list()
    for (column in names(data)) {
      label <- attr(data[[column]], "label")
      values <- haven::zap_labels(data[[column]])
      attributes(values)[c("label", "format.sas")] <- NULL
      columns[[column]] <- c(list(label = if (is.null(label)) "" else label), profile_column(values, arms, keys, data))
    }
    list(records = nrow(data), armVariable = if (is.na(arm_variable)) NULL else arm_variable, keys = I(keys), columns = columns)
  }, error = function(problem) list(error = conditionMessage(problem)))
}
jsonlite::write_json(profiles, output, auto_unbox = TRUE, null = "null", digits = NA)
