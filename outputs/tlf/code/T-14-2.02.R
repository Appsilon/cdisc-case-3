# Name: T-14-2.02.R
# Title: Summary of HAMD 17 Total Score at Baseline
# Spec:  AN-14-2.02  (analysis-spec.json)
# Population: Intent-to-Treat Population  |  Dataset: ADRSHAMD
# Subset: PARAMCD = 'HAMD118' AND ABLFL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-2.02.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-2.02"
spec <- SPECS[["AN-14-2.02"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_desc_cont(ID, spec, vars = "AVAL",
  labels = list(AVAL = "HAMD 17 Total Score at Baseline"),
  extra_note = "Recategorized from section 14-3 to 14-2 at plan review (critic finding R-3): HAMD 17 has no scheduled post-baseline visit, so this is a baseline characteristic rather than a treatment-effect analysis. See issues.md — a Week-24 change-from-baseline analysis IS derivable (n=6) from the early-discontinuation records if you want it.")
