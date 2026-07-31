# Name: T-14-1.03.R
# Title: Summary of Number of Subjects by Site
# Spec:  AN-14-1.03  (analysis-spec.json)
# Population: All Enrolled Subjects  |  Dataset: ADSL
# Subset: (all records)
# ----------------------------------------------------------------------------
# ARD-first: Phase A computes every statistic into <id>/ard.csv, Phase B renders
# <id>/T-14-1.03.generated.md from that ARD. No value is hand-entered.
if (!exists("SPECS")) {
  d <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
  source(file.path(d, "00_setup.R")); source(file.path(d, "01_engines.R"))
  source(file.path(d, "02_engines_model.R")); source(file.path(d, "03_engines_shift_km.R"))
  source(file.path(d, "04_engines_misc.R"))
}
ID <- "T-14-1.03"
spec <- SPECS[["AN-14-1.03"]]
cat("\n>>>", ID, "-", spec$title, "\n")
gen_cat_freq(ID, spec, vars = c("SITEID", "SITEGR1"),
  labels = list(SITEID = "Investigational site", SITEGR1 = "Pooled site group (MANDATORY RULE 3)"),
  dataset = "ADSL", denom_pop = "All Subjects",
  extra_note = "Both the raw site and the derived pooled site group are shown so the reviewer can verify the <3-randomized pooling rule directly.")
