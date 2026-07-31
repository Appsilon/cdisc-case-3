# Name: T-14-4.01.R
# Title: Summary of Planned Exposure to Study Drug
# Spec:  AN-14-4.01  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADEX
# Subset: PARAMCD IN ('TRTDUR','CUMDOSE','AVGDD')
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-4.01.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-4.01"
spec <- SPECS[["AN-14-4.01"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_desc_cont(ID, spec, vars = "AVAL",
  labels = list(AVAL = "Exposure"), by_param = TRUE,
  digits = c(N = 0, mean = 1, sd = 2, median = 1, min = 0, max = 0))
