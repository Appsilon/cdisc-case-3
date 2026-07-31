# Name: T-14-3.01.R
# Title: Change from Baseline to Week 24 in PHQ-9 Total Score - LOCF
# Spec:  AN-14-3.01  (analysis-spec.json)
# Population: Efficacy Population  |  Dataset: ADQSPHQ
# Subset: PARAMCD = 'PHQTOT' AND AVISITN = 24 AND ANL01FL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-3.01.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-3.01"
spec <- SPECS[["AN-14-3.01"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_ancova(ID, spec)
