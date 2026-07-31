# Name: T-14-7.01.R
# Title: Summary of Vital Signs at Baseline and End of Treatment
# Spec:  AN-14-7.01  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADVS
# Subset: PARAMCD IN ('SYSBPST','SYSBPSU','DIABPST','DIABPSU','PULSEST','PULSESU','TEMP','WEIGHT') AND AVISITN IN (0, 24) AND ANL01FL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-7.01.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-7.01"
spec <- SPECS[["AN-14-7.01"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_desc_cont(ID, spec, vars = "AVAL", labels = list(AVAL = "Value"),
  by_param = TRUE, by_visit = TRUE,
  extra_note = "Blood pressure and pulse are reported separately for the STANDING and SUPINE positions, as USDM endpoint END4 requires; collapsing across position would average two different measurements.")
