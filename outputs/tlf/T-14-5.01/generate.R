# Name: T-14-5.01.R
# Title: Incidence of Treatment-Emergent Adverse Events by System Organ Class and Preferred Term
# Spec:  AN-14-5.01  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADAE
# Subset: TRTEMFL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-5.01.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-5.01"
spec <- SPECS[["AN-14-5.01"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_incidence(ID, spec)
