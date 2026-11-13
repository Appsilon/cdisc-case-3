# ADVS - one parameter only (test fixture): guards the single-PARAMCD manifest case
library(dplyr, warn.conflicts = FALSE)

vs <- haven::read_xpt(file.path(Sys.getenv("SDTM_DIR"), "vs.xpt"))

# @derive ADVS.STUDYID,ADVS.USUBJID origin=Predecessor src=VS.*
# @derive ADVS.PARAMCD origin=Predecessor src=VS.VSTESTCD
# @derive ADVS.AVAL origin=Derived src=VS.VSSTRESN method="Standard numeric result"
# @derive ADVS.ADY origin=Derived src=VS.VSDY method="Study day of the assessment"
advs <- vs %>% filter(VSTESTCD == "WEIGHT", !is.na(VSSTRESN)) %>%
  transmute(STUDYID, USUBJID, PARAMCD = VSTESTCD, AVAL = VSSTRESN, ADY = as.numeric(VSDY))

labels <- c(STUDYID = "Study Identifier", USUBJID = "Unique Subject Identifier", PARAMCD = "Parameter Code",
            AVAL = "Analysis Value", ADY = "Analysis Relative Day")
for (name in names(labels)) attr(advs[[name]], "label") <- labels[[name]]
saveRDS(advs, file.path(Sys.getenv("ADAM_DIR"), "advs.rds"))
