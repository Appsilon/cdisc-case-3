# Name: T-14-7.04.R
# Title: Summary of Concomitant Medications
# Spec:  AN-14-7.04  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADCM
# Subset: (all concomitant-medication records)
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-7.04.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-7.04"
spec <- SPECS[["AN-14-7.04"]]
cat("\n>>>", ID, "-", spec$title, "\n")
# CMCLASX is now a real ADCM column carrying an explicit "uncoded" placeholder,
# derived in 03_safety.R. (Shadowing read_adam here did NOT work: run_all sources
# each script into its own env, so the engine still resolved the original
# function and the hierarchy silently collapsed to a single row.)
gen_incidence(ID, spec, soc = "CMCLASX", pt = "CMTRT", count_events = FALSE,
  extra_note = "Concomitant medications are NOT WHO-DD coded in this extract (no CMDECOD, no CMCLAS/CMATC), so no therapeutic-class hierarchy is producible. Medications are summarized by verbatim CMTRT under a single explicit placeholder class. Critic finding R-6.")
