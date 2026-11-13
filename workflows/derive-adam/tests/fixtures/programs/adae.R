# ADAE - adverse events analysis dataset (test fixture standing in for the agent)
library(dplyr, warn.conflicts = FALSE)

ae <- haven::read_xpt(file.path(Sys.getenv("SDTM_DIR"), "ae.xpt"))
adsl <- readRDS(file.path(Sys.getenv("ADAM_DIR"), "adsl.rds"))

# @derive ADAE.STUDYID,ADAE.USUBJID,ADAE.AETERM origin=Predecessor src=AE.*
# @derive ADAE.AESEV origin=Predecessor src=AE.*
adae <- ae %>% select(STUDYID, USUBJID, AETERM, AESEV, AESTDTC)

# @derive ADAE.TRT01P,ADAE.SAFFL origin=Predecessor src=ADSL.*
# @derive ADAE.TRTSDT origin=Predecessor src=ADSL.TRTSDT
adae <- adae %>% left_join(adsl %>% select(USUBJID, TRT01P, SAFFL, TRTSDT), by = "USUBJID")

# @derive ADAE.ASTDT origin=Derived src=AE.AESTDTC method="AESTDTC as a date"
adae <- adae %>% mutate(ASTDT = as.Date(AESTDTC))
# @derive ADAE.TRTEMFL origin=Derived src=ADAE.ASTDT,ADSL.TRTSDT method="Y when the AE starts on or after first exposure"
adae <- adae %>% mutate(TRTEMFL = if_else(!is.na(ASTDT) & !is.na(TRTSDT) & ASTDT >= TRTSDT, "Y", "N"))

adae <- adae %>% select(-AESTDTC)
labels <- c(STUDYID = "Study Identifier", USUBJID = "Unique Subject Identifier", AETERM = "Reported Term for the Adverse Event",
            AESEV = "Severity/Intensity", TRT01P = "Planned Treatment for Period 01", SAFFL = "Safety Population Flag",
            TRTSDT = "Date of First Exposure to Treatment", ASTDT = "Analysis Start Date", TRTEMFL = "Treatment Emergent Analysis Flag")
for (name in names(labels)) attr(adae[[name]], "label") <- labels[[name]]
saveRDS(adae, file.path(Sys.getenv("ADAM_DIR"), "adae.rds"))
