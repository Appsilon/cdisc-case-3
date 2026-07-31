# Name: T-14-2.01.R
# Title: Summary of Demographic and Baseline Characteristics
# Spec:  AN-14-2.01  (analysis-spec.json)
# Population: Intent-to-Treat Population  |  Dataset: ADSL
# Subset: ITTFL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-2.01.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-2.01"
spec <- SPECS[["AN-14-2.01"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_demographics(ID, spec)
