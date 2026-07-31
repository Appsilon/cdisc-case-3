# Name: T-14-7.03.R
# Title: Summary of Weight Change from Baseline at End of Treatment
# Spec:  AN-14-7.03  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADVS
# Subset: PARAMCD = 'WEIGHT' AND AVISITN = 24 AND ANL01FL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-7.03.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-7.03"
spec <- SPECS[["AN-14-7.03"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_desc_cont(ID, spec, vars = c("BASE", "AVAL", "CHG"),
  labels = list(BASE = "Baseline weight (kg)", AVAL = "End of Treatment weight (kg)",
                CHG = "Change from Baseline (kg)"))
