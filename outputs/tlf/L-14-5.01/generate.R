# Name: L-14-5.01.R
# Title: Listing of Deaths
# Spec:  AN-L-14-5.01  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADSL
# Subset: DTHFL = 'Y'
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/L-14-5.01.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "L-14-5.01"
spec <- SPECS[["AN-L-14-5.01"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_listing(ID, spec, join_ae = TRUE,
  cols = c("USUBJID", "TRT01A", "SITEID", "AGE", "SEX", "DTHDT", "DTHDY", "DTHCAUS", "AEDECOD", "DCSREAS"),
  labels = list(USUBJID = "Subject", TRT01A = "Actual treatment", SITEID = "Site", AGE = "Age",
                SEX = "Sex", DTHDT = "Date of death", DTHDY = "Study day", DTHCAUS = "Primary cause of death (SDTM DD)",
                AEDECOD = "Associated fatal AE", DCSREAS = "Discontinuation reason"))
