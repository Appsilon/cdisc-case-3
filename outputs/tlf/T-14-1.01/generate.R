# Name: T-14-1.01.R
# Title: Summary of Populations
# Spec:  AN-14-1.01  (analysis-spec.json)
# Population: All Enrolled Subjects  |  Dataset: ADSL
# Subset: (all records)
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-1.01.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-1.01"
spec <- SPECS[["AN-14-1.01"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_cat_freq(ID, spec,
  vars = c("ITTFL", "SAFFL", "EFFFL", "COMPLFL"),
  labels = list(ITTFL = "Intent-to-Treat population", SAFFL = "Safety population",
                EFFFL = "Efficacy population", COMPLFL = "Completers population"),
  dataset = "ADSL", denom_pop = "All Subjects",
  extra_note = "Denominator is all enrolled subjects with a planned arm. This table defines the analysis-set denominators every other display cites.")
