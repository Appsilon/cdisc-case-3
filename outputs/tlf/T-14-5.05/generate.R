# Name: T-14-5.05.R
# Title: Incidence of Treatment-Emergent Adverse Events by Maximum Severity
# Spec:  AN-14-5.05  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADAE
# Subset: TRTEMFL = 'Y' AND AOCC01FL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-5.05.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-5.05"
spec <- SPECS[["AN-14-5.05"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_incidence(ID, spec, extra_group = "ASEV", count_events = FALSE,
  extra_note = "Subjects are counted ONCE at their maximum severity per preferred term, via the ADaM occurrence flag AOCC01FL. Counting all records instead would double-count subjects.")
