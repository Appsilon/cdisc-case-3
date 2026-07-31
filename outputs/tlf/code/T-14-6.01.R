# Name: T-14-6.01.R
# Title: Summary Statistics for Continuous Laboratory Values and Change from Baseline
# Spec:  AN-14-6.01  (analysis-spec.json)
# Population: Safety Population  |  Dataset: ADLB
# Subset: PARCAT1 IN ('CHEMISTRY','HEMATOLOGY','URINALYSIS') AND ANL01FL = 'Y' AND AVAL IS NOT NULL
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-6.01.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-6.01"
spec <- SPECS[["AN-14-6.01"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_desc_cont(ID, spec, vars = c("BASE", "AVAL", "CHG"),
  labels = list(BASE = "Baseline", AVAL = "Value", CHG = "Change from Baseline"),
  by_param = TRUE,
  extra_note = "Qualitative tests (ANISO, COLOR, KETONES, MACROCY, POIKILO, UROBIL) are excluded — they have no numeric result. Analysis visits come from day-based windowing, so unscheduled visits are retained.")
