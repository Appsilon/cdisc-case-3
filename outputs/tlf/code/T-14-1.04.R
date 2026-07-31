# Name: T-14-1.04.R
# Title: Summary of Medical History
# Spec:  AN-14-1.04  (analysis-spec.json)
# Population: Intent-to-Treat Population  |  Dataset: ADSL
# Subset: ITTFL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-1.04.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-1.04"
spec <- SPECS[["AN-14-1.04"]]
cat("\n>>>", ID, "-", spec$title, "\n")
# ADMH is a real derived dataset now (03_safety.R). It is UNCODED: MHBODSYS is an
# explicit placeholder and the "preferred term" is the verbatim MHTERM.
spec$dataSubset$dataset <- "ADMH"; spec$dataSubset$condition <- "ITTFL = 'Y'"
gen_incidence(ID, spec, soc = "MHBODSYS", pt = "MHDECOD", count_events = FALSE,
  extra_note = "Medical history is UNCODED in this extract (no MHDECOD/MHBODSYS in SDTM), so the system-organ-class level is an explicit placeholder and the term is the verbatim MHTERM. Critic finding R-5 flagged this table as a prune candidate; it is retained so the ICH E3 11.2 expectation is visibly addressed.")
