# ADSL - subject-level analysis dataset (test fixture standing in for the agent)
library(dplyr, warn.conflicts = FALSE)
library(admiral, warn.conflicts = FALSE)

dm <- haven::read_xpt(file.path(Sys.getenv("SDTM_DIR"), "dm.xpt"))
ex <- haven::read_xpt(file.path(Sys.getenv("SDTM_DIR"), "ex.xpt"))

# ---- Predecessors ----
# @derive ADSL.STUDYID,ADSL.USUBJID,ADSL.SUBJID,ADSL.SITEID,ADSL.AGE,ADSL.SEX origin=Predecessor src=DM.*
adsl <- dm %>% select(STUDYID, USUBJID, SUBJID, SITEID, AGE, SEX, ARM, ARMCD)

# ---- Treatment ----
# @derive ADSL.TRT01P origin=Derived src=DM.ARM,DM.ARMCD method="Planned arm; screen failures (ARMCD Scrnfail) and blank ARM stay missing"
adsl <- adsl %>% mutate(TRT01P = if_else(ARM == "" | ARMCD == "Scrnfail", NA_character_, ARM))
# @derive ADSL.TRT01PN origin=Derived src=DM.ARMCD method="Planned dose in mg: Pbo 0, Xan_Lo 54, Xan_Hi 81"
adsl <- adsl %>% mutate(TRT01PN = unname(c(Pbo = 0, Xan_Lo = 54, Xan_Hi = 81)[ARMCD]))

# @derive ADSL.TRTSDT origin=Derived src=EX.EXSTDTC,EX.EXDOSE method="Date of the first exposure with a recorded dose (placebo EXDOSE = 0 counts)"
ex_dosed <- ex %>% filter(EXDOSE >= 0) %>% derive_vars_dt(new_vars_prefix = "EXST", dtc = EXSTDTC)
adsl <- derive_vars_merged(adsl, dataset_add = ex_dosed, by_vars = exprs(STUDYID, USUBJID),
                           new_vars = exprs(TRTSDT = EXSTDT), order = exprs(EXSTDT), mode = "first")

# ---- Populations ----
# @derive ADSL.ITTFL origin=Derived src=DM.ARM method="Y when a planned arm was assigned"
adsl <- adsl %>% mutate(ITTFL = if_else(is.na(TRT01P), "N", "Y"))
# @derive ADSL.SAFFL origin=Derived src=EX.EXSTDTC method="Y when randomized and exposed (any EX record)"
adsl <- adsl %>% mutate(SAFFL = if_else(ITTFL == "Y" & !is.na(TRTSDT), "Y", "N"))

if (sum(adsl$SAFFL == "Y") == 0) stop("DATA-QUALITY GATE FAILED: no safety subjects")

adsl <- adsl %>% select(-ARM, -ARMCD)
labels <- c(STUDYID = "Study Identifier", USUBJID = "Unique Subject Identifier", SUBJID = "Subject Identifier for the Study",
            SITEID = "Study Site Identifier", AGE = "Age", SEX = "Sex", TRT01P = "Planned Treatment for Period 01",
            TRT01PN = "Planned Treatment for Period 01 (N)", TRTSDT = "Date of First Exposure to Treatment",
            ITTFL = "Intent-To-Treat Population Flag", SAFFL = "Safety Population Flag")
for (name in names(labels)) attr(adsl[[name]], "label") <- labels[[name]]
saveRDS(adsl, file.path(Sys.getenv("ADAM_DIR"), "adsl.rds"))
