# Name: F-14-1.R
# Title: Time to First Injection-Site Reaction by Treatment Group (Kaplan-Meier)
# Spec:  AN-F-14-1  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADTTE
# Subset: PARAMCD = 'TTISR'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/F-14-1.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "F-14-1"
spec <- SPECS[["AN-F-14-1"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_km(ID, spec)
