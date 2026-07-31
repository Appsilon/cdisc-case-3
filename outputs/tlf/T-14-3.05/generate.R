# Name: T-14-3.05.R
# Title: PHQ-9 Total Score - Mean and Mean Change from Baseline Over Time
# Spec:  AN-14-3.05  (analysis-spec.json)
# Population: Efficacy Population  |  Dataset: ADQSPHQ
# Subset: PARAMCD = 'PHQTOT' AND ANL02FL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-3.05.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-3.05"
spec <- SPECS[["AN-14-3.05"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_desc_cont(ID, spec, vars = c("AVAL", "CHG"),
  labels = list(AVAL = "PHQ-9 Total Score", CHG = "Change from Baseline"),
  by_visit = TRUE,
  extra_note = "Observed cases only (ANL02FL). This display is the honest picture of the data behind T-14-3.01: it shows how few subjects contribute at each post-baseline visit.")
