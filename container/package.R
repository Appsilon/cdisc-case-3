#!/usr/bin/env Rscript
# =============================================================================
# Step 5 (package): the deterministic validation + packaging boundary.
#
# Reads the ARS Reporting Event + the agent's /workspace/{ard,tfl,coverage.json}
# and produces the downloadable /output:
#   1. Coverage gate  — every ARS Output MUST have a rendered file AND an ARD,
#                       else non-zero exit (the conformance test).
#   2. ard.csv        — all per-output ARDs consolidated into one long-skinny
#                       results-by-row frame (the reusable results artifact).
#   3. reporting_event_with_results.json — results written back into each
#                       Analysis.results[] (spec in, completed spec out).
#   4. traceability.html — the interactive Objective -> Endpoint -> Output ->
#                       Analysis -> Method -> ADaM graph (built by build_trace.py
#                       from this run's artifacts). traceability_table.html is the
#                       detailed row view: Output -> Analysis -> dataset.variable
#                       -> population -> SAP reference, stamped with ARS ids
#                       (lineage by construction, not inferred — see PLAN-3 §7).
#   5. manifest.json  — study id, counts, standard/custom split, repairs,
#                       pass/fail, per-output lineage.
#
# Usage: Rscript package.R --ars <re.json> --work <workspace> --out <output>
# =============================================================================

suppressMessages({
  library(jsonlite)
})

# --- args --------------------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
get_arg <- function(flag, default) {
  i <- match(flag, args)
  if (!is.na(i) && i < length(args)) args[[i + 1]] else default
}
ars_path <- get_arg("--ars", "/workspace/reporting_event.json")
work <- get_arg("--work", "/workspace")
out <- get_arg("--out", "/output")
dir.create(out, recursive = TRUE, showWarnings = FALSE)

ars <- fromJSON(ars_path, simplifyVector = FALSE)

# --- output -> analysisIds, from the ARS mainListOfContents ------------------
collect_analyses <- function(node, acc = character()) {
  if (is.null(node)) return(acc)
  items <- node$contentsList$listItems %||% node$listItems %||% NULL
  if (is.null(items)) return(acc)
  for (it in items) {
    if (!is.null(it$analysisId)) acc <- c(acc, it$analysisId)
    if (!is.null(it$sublist)) acc <- collect_analyses(it$sublist, acc)
  }
  acc
}
`%||%` <- function(a, b) if (!is.null(a)) a else b

# Walk the LOPA tree; associate every outputId with the analysisIds beneath it.
output_analyses <- list()
walk_output <- function(items) {
  for (it in items) {
    if (!is.null(it$outputId)) {
      output_analyses[[it$outputId]] <<- collect_analyses(it$sublist)
    }
    if (!is.null(it$sublist) && is.null(it$outputId)) walk_output(it$sublist$contentsList$listItems %||% it$sublist$listItems %||% list())
  }
}
top_items <- ars$mainListOfContents$contentsList$listItems %||% list()
walk_output(top_items)

output_ids <- vapply(ars$outputs, function(o) o$id, character(1))
output_names <- setNames(vapply(ars$outputs, function(o) o$name %||% o$id, character(1)), output_ids)

# lookups: analysis by id, method by id, grouping by id, analysisSet by id
by_id <- function(coll) setNames(coll, vapply(coll, function(x) x$id, character(1)))
analyses <- by_id(ars$analyses)
methods <- by_id(ars$methods)
groupings <- by_id(ars$analysisGroupings %||% list())
sets <- by_id(ars$analysisSets %||% list())

# --- 1. Coverage gate --------------------------------------------------------
ard_dir <- file.path(work, "ard")
tfl_dir <- file.path(work, "tfl")
# Rendered files for an output id: <oid>.<ext> in tfl/ (no regex — exact prefix).
tfl_files_for <- function(oid) {
  files <- list.files(tfl_dir)
  files[startsWith(files, paste0(oid, "."))]
}
missing <- list()
for (oid in output_ids) {
  ard_ok <- file.exists(file.path(ard_dir, paste0(oid, ".csv")))
  tfl_ok <- length(tfl_files_for(oid)) > 0
  if (!ard_ok || !tfl_ok) {
    missing[[oid]] <- list(ard = ard_ok, tfl = tfl_ok)
  }
}

# --- 2. Consolidate ARDs into one long-skinny ard.csv ------------------------
ard_files <- list.files(ard_dir, pattern = "\\.csv$", full.names = TRUE)
all_ard <- if (length(ard_files)) {
  do.call(rbind, lapply(ard_files, function(f) {
    df <- read.csv(f, stringsAsFactors = FALSE, colClasses = "character")
    if (!"output_id" %in% names(df)) df$output_id <- sub("\\.csv$", "", basename(f))
    df
  }))
} else data.frame()
if (nrow(all_ard)) write.csv(all_ard, file.path(out, "ard.csv"), row.names = FALSE, na = "")

# --- 3. Results write-back into Analysis.results[] ---------------------------
# Map a computed group_level string back to an ARS groupId within a grouping.
group_id_for <- function(grouping_id, level) {
  g <- groupings[[grouping_id]]
  if (is.null(g) || is.na(level)) return(NULL)
  for (grp in g$groups) {
    vals <- unlist(grp$condition$value %||% list())
    if (identical(grp$name, level) || (length(vals) && level %in% vals)) return(grp$id)
  }
  NULL
}

build_results <- function(aid) {
  rows <- all_ard[all_ard$analysis_id == aid & !is.na(all_ard$operation_id) & all_ard$operation_id != "", , drop = FALSE]
  if (!nrow(rows)) return(NULL)
  an <- analyses[[aid]]
  grouping_id <- if (!is.null(an$orderedGroupings) && length(an$orderedGroupings)) an$orderedGroupings[[1]]$groupingId else NULL
  lapply(seq_len(nrow(rows)), function(i) {
    r <- rows[i, ]
    res <- list(operationId = r$operation_id, rawValue = r$stat_raw, formattedValue = r$stat_fmt %||% r$stat_raw)
    gid <- if (!is.null(grouping_id)) group_id_for(grouping_id, r$group_level) else NULL
    if (!is.null(gid)) res$resultGroups <- list(list(groupingId = grouping_id, groupId = gid))
    res
  })
}

n_results <- 0
for (i in seq_along(ars$analyses)) {
  aid <- ars$analyses[[i]]$id
  results <- build_results(aid)
  if (!is.null(results)) {
    ars$analyses[[i]]$results <- results
    n_results <- n_results + length(results)
  }
}
write_json(ars, file.path(out, "reporting_event_with_results.json"),
           auto_unbox = TRUE, pretty = TRUE, null = "null")

# --- 4. traceability.html ----------------------------------------------------
esc <- function(s) { s <- as.character(s %||% ""); gsub("<", "&lt;", gsub("&", "&amp;", s)) }
coverage_path <- file.path(work, "coverage.json")
coverage <- if (file.exists(coverage_path)) fromJSON(coverage_path, simplifyVector = FALSE) else NULL
mode_for <- function(oid) {
  if (is.null(coverage)) return("standard")
  for (c in coverage$outputs %||% list()) if (identical(c$outputId, oid)) return(c$mode %||% "standard")
  "standard"
}

rows_html <- character()
for (oid in output_ids) {
  aids <- output_analyses[[oid]] %||% unique(all_ard$analysis_id[all_ard$output_id == oid])
  mode <- mode_for(oid)
  tfl <- tfl_files_for(oid)
  tfl_link <- if (length(tfl)) sprintf("<a href='./tfl/%s'>%s</a>", tfl[[1]], tfl[[1]]) else "<em>missing</em>"
  n_ard <- sum(all_ard$output_id == oid)
  for (aid in aids) {
    an <- analyses[[aid]]
    if (is.null(an)) next
    m <- methods[[an$methodId]]
    set <- sets[[an$analysisSetId]]
    set_cond <- if (!is.null(set$condition)) sprintf("%s.%s %s %s", set$condition$dataset, set$condition$variable,
                                                      set$condition$comparator, paste(unlist(set$condition$value), collapse = ",")) else esc(set$label %||% an$analysisSetId)
    docref <- ""
    if (!is.null(an$documentRefs) && length(an$documentRefs)) {
      dr <- an$documentRefs[[1]]
      pr <- if (!is.null(dr$pageRefs) && length(dr$pageRefs)) dr$pageRefs[[1]]$label else ""
      docref <- sprintf("%s: %s", esc(dr$referenceDocumentId), esc(pr))
    }
    rows_html <- c(rows_html, sprintf(
      "<tr><td><code>%s</code><br><small>%s</small></td><td><span class='mode %s'>%s</span></td><td><code>%s</code><br><small>%s</small></td><td><code>%s.%s</code></td><td>%s</td><td>%s</td><td><span class='dir'>[direct]</span> %s</td><td>%s</td></tr>",
      esc(oid), esc(output_names[[oid]]), mode, mode,
      esc(aid), esc(an$name), esc(an$dataset), esc(an$variable),
      esc(set_cond), esc(m$name %||% an$methodId), docref, tfl_link))
  }
  if (!length(aids)) {
    rows_html <- c(rows_html, sprintf("<tr><td><code>%s</code><br><small>%s</small></td><td><span class='mode %s'>%s</span></td><td colspan='5'><em>no analyses linked in ARS list of contents</em></td><td>%s</td></tr>",
                                      esc(oid), esc(output_names[[oid]]), mode, mode, tfl_link))
  }
}

study_id <- ars$id %||% "(reporting event)"
html <- sprintf("<!doctype html><html><head><meta charset='utf-8'><title>Traceability table — %s</title>
<style>
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:2rem;color:#1a1a2e}
h1{font-size:1.4rem} .sub{color:#666;margin-bottom:1.5rem}
table{border-collapse:collapse;width:100%%;font-size:13px} th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#0b3d64;color:#fff;position:sticky;top:0} tr:nth-child(even){background:#f7f9fc}
code{background:#eef2f7;padding:1px 4px;border-radius:3px;font-size:12px} small{color:#666}
.mode{font-size:11px;padding:2px 6px;border-radius:10px;font-weight:600}
.standard{background:#d7f0dd;color:#0a6b2f} .custom{background:#fde4c8;color:#a5560a}
.dir{color:#0a6b2f;font-weight:600} .legend{margin:1rem 0;font-size:12px;color:#444}
.legend b{color:#0a6b2f}
</style></head><body>
<h1>End-to-end traceability — %s</h1>
<div class='sub'>%s &middot; every row links a rendered output cell back to its analysis, ADaM variable, analysis population and SAP reference. Lineage is carried through execution, not inferred.</div>
<div class='legend'>Trace strength &mdash; <b>[direct]</b>: exact evidence, stamped with the ARS analysis/operation id that produced the cell. (The 2025 winning tool <i>reconstructed</i> lineage and labelled its confidence [direct]/[reasoned]/[general]; here every structural link is [direct] because the pipeline never lost the lineage.)</div>
<table><thead><tr><th>Output</th><th>Mode</th><th>Analysis</th><th>ADaM var</th><th>Population</th><th>Method</th><th>SAP reference</th><th>Rendered</th></tr></thead>
<tbody>%s</tbody></table>
</body></html>",
  esc(study_id), esc(ars$name %||% study_id), esc(ars$name %||% ""), paste(rows_html, collapse = "\n"))
# The detailed row table is the secondary view; the interactive graph (built
# below by build_trace.py) is the headline traceability.html.
writeLines(html, file.path(out, "traceability_table.html"))

# --- copy tfl + ard dirs to /output ------------------------------------------
if (dir.exists(tfl_dir)) file.copy(tfl_dir, out, recursive = TRUE)
if (dir.exists(ard_dir)) file.copy(ard_dir, out, recursive = TRUE)

# --- 5. manifest.json + coverage gate exit -----------------------------------
per_output <- lapply(output_ids, function(oid) {
  list(outputId = oid, name = unname(output_names[[oid]]), mode = mode_for(oid),
       analysisIds = output_analyses[[oid]] %||% unique(all_ard$analysis_id[all_ard$output_id == oid]),
       ardRows = sum(all_ard$output_id == oid),
       rendered = length(tfl_files_for(oid)) > 0,
       covered = is.null(missing[[oid]]))
})
n_std <- sum(vapply(output_ids, function(o) mode_for(o) == "standard", logical(1)))
manifest <- list(
  status = if (length(missing) == 0) "success" else "coverage_failed",
  reportingEventId = ars$id, reportingEventName = ars$name,
  outputsExpected = length(output_ids),
  outputsCovered = length(output_ids) - length(missing),
  standardOutputs = n_std, customOutputs = length(output_ids) - n_std,
  analysesWithResults = sum(vapply(ars$analyses, function(a) !is.null(a$results), logical(1))),
  operationResultsWritten = n_results,
  ardRows = nrow(all_ard),
  missing = missing,
  perOutput = per_output
)
write_json(manifest, file.path(out, "manifest.json"), auto_unbox = TRUE, pretty = TRUE, null = "null")

# --- 6. interactive traceability graph (headline traceability.html) ----------
# Best-effort: build_trace.py never fails the run; the coverage gate below is the
# conformance test. It consumes the artifacts written above (results-written-back
# ARS, coverage, manifest, ard.csv) + the bundled USDM objective/endpoint fixture.
trace_rc <- tryCatch(
  system2("python3", c("/app/container/build_trace.py",
    "--ars", file.path(out, "reporting_event_with_results.json"),
    "--ars-fallback", ars_path,
    "--usdm", "/app/fixtures/usdm_trace.json",
    "--coverage", file.path(work, "coverage.json"),
    "--manifest", file.path(out, "manifest.json"),
    "--ard", file.path(out, "ard.csv"),
    "--template", "/app/viz/traceability.template.html",
    "--out", file.path(out, "traceability.html")),
    stdout = TRUE, stderr = TRUE),
  error = function(e) { message("build_trace.py skipped: ", conditionMessage(e)); NULL })
if (!is.null(trace_rc)) cat(paste(trace_rc, collapse = "\n"), "\n")
if (!file.exists(file.path(out, "traceability.html"))) {
  # fall back to the row table as traceability.html so the output always exists
  file.copy(file.path(out, "traceability_table.html"), file.path(out, "traceability.html"), overwrite = TRUE)
}

cat(sprintf("Coverage: %d/%d outputs (%d standard, %d custom) | %d ARD rows | %d operation results written\n",
            manifest$outputsCovered, manifest$outputsExpected, n_std, length(output_ids) - n_std,
            nrow(all_ard), n_results))
if (length(missing) > 0) {
  cat("COVERAGE GATE FAILED — missing artifacts for:\n")
  for (oid in names(missing)) cat(sprintf("  %s (ard=%s, tfl=%s)\n", oid, missing[[oid]]$ard, missing[[oid]]$tfl))
  quit(status = 1)
}
cat("Coverage gate passed. Wrote ard.csv, reporting_event_with_results.json, traceability.html (interactive) + traceability_table.html, manifest.json\n")
