# Name: T-14-3.04.R
# Title: Repeated Measures Analysis of Change from Baseline to Week 24 in PHQ-9 Total Score
# Spec:  AN-14-3.04  (analysis-spec.json)
# Population: Efficacy Population  |  Dataset: ADQSPHQ
# Subset: PARAMCD = 'PHQTOT' AND AVISITN > 0 AND DTYPE = '' AND ANL02FL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-3.04.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-3.04"
spec <- SPECS[["AN-14-3.04"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_mmrm(ID, spec)
