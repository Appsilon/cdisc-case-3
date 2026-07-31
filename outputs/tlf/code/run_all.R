# Name: run_all.R
# Description: Run every TLF script in section order, collect status, emit the
#              TLF index and issues report.
# ----------------------------------------------------------------------------
d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
source(file.path(d, "04_engines_misc.R"))

IDS <- c("T-14-1.01", "T-14-1.02", "T-14-1.03", "T-14-1.04", "T-14-2.01", "T-14-2.02", "T-14-3.01", "T-14-3.02", "T-14-3.03", "T-14-3.04", "T-14-3.05", "T-14-4.01", "T-14-5.01", "T-14-5.02", "T-14-5.03", "T-14-5.04", "T-14-5.05", "T-14-5.06", "L-14-5.01", "T-14-6.01", "T-14-6.02", "T-14-6.03", "T-14-6.04", "T-14-6.05", "T-14-6.06", "T-14-7.01", "T-14-7.02", "T-14-7.03", "T-14-7.04", "F-14-1")
STATUS <- list()
for (id in IDS) {
  t0 <- Sys.time()
  r <- try(source(file.path(d, paste0(id, ".R")), local = new.env()), silent = TRUE)
  err <- if (inherits(r, "try-error")) trimws(gsub("\\s+", " ", as.character(r))) else ""
  dd <- file.path(TLF_DIR, id)
  STATUS[[length(STATUS)+1]] <- data.frame(
    id = id,
    ard = file.exists(file.path(dd, "ard.csv")),
    display = file.exists(file.path(dd, paste0(id, ".generated.md"))),
    png = file.exists(file.path(dd, paste0(id, ".png"))),
    secs = round(as.numeric(difftime(Sys.time(), t0, units = "secs")), 1),
    error = err, stringsAsFactors = FALSE)
  if (nzchar(err)) { cat("    !! ERROR:", err, "\n"); note_issue(id, "ERROR", err) }
  # copy the generating script next to its outputs for traceability
  if (dir.exists(dd)) file.copy(file.path(d, paste0(id, ".R")),
                                file.path(dd, "generate.R"), overwrite = TRUE)
}
ST <- do.call(rbind, STATUS)
cat("\n================ RUN SUMMARY ================\n"); print(ST[, c("id","ard","display","png","secs")], row.names = FALSE)
cat(sprintf("\nARD produced: %d/%d | displays produced: %d/%d | errors: %d\n",
            sum(ST$ard), nrow(ST), sum(ST$display), nrow(ST), sum(nzchar(ST$error))))
saveRDS(ST, file.path(TLF_DIR, ".status.rds"))
source(file.path(d, "05_reports.R"))
