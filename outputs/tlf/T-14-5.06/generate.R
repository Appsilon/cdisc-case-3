# Name: T-14-5.06.R
# Title: Incidence of Treatment-Emergent Adverse Events by Relationship to Study Drug
# Spec:  AN-14-5.06  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADAE
# Subset: TRTEMFL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-5.06.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-5.06"
spec <- SPECS[["AN-14-5.06"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_incidence(ID, spec, extra_group = "AREL", count_events = FALSE,
  extra_note = "AEREL levels in the source data are RELATED / POSSIBLY RELATED / UNLIKELY RELATED / NOT RELATED. They are shown as collected; no pooling into a binary related/not-related has been applied, since no SAP defines it.")
