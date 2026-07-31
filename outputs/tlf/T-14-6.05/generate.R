# Name: T-14-6.05.R
# Title: Shifts of Laboratory Values During Treatment, Categorized Based on Threshold Ranges
# Spec:  AN-14-6.05  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADLB
# Subset: ANL01FL = 'Y' AND ANRIND IS NOT NULL AND WORSTFL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-6.05.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-6.05"
spec <- SPECS[["AN-14-6.05"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_shift(ID, spec, cmh = TRUE)
