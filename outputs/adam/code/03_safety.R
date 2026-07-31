# Name: 03_safety.R
# Description: Generate ADAE, ADLB, ADVS, ADEX, ADCM, ADTTE
#              — satisfies adam-spec.json datasets of the same names.
# Supports tables: 14-1.02, 14-4.01, 14-5.01..06, L-14-5.01, 14-6.01..06,
#                  14-7.01..04, F-14-1
# Implements MANDATORY RULE 1 (day-based windowing) and RULE 2 (LOCF endpoint)
# on the BDS datasets (ADLB, ADVS).
# ----------------------------------------------------------------------------
source("00_setup.R")

adsl <- read_adam("ADSL")
SUBJ <- adsl %>% select(USUBJID, TRTP, TRT01P, TRT01PN, TRT01A, SITEGR1, SITEID,
                        TRTSDT, TRTEDT, ITTFL, SAFFL, EFFFL, COMPLFL)
ENDPT_N <- 24; ENDPT_LAB <- "Week 24"; ENDPT_DAY <- 169

# Full study visit schedule for the routinely-collected safety domains.
FULL_T  <- c("Baseline" = 1, "Week 2" = 15, "Week 4" = 29, "Week 6" = 43,
             "Week 8" = 57, "Week 12" = 85, "Week 16" = 113, "Week 20" = 141,
             "Week 24" = 169, "Week 26" = 183)
FULL_VN <- c("Baseline" = 0, "Week 2" = 2, "Week 4" = 4, "Week 6" = 6,
             "Week 8" = 8, "Week 12" = 12, "Week 16" = 16, "Week 20" = 20,
             "Week 24" = 24, "Week 26" = 26)

# ================================================================== ADAE
cat("\n===== ADAE =====\n")
ae <- read_sdtm("AE")
adae <- ae %>%
  mutate(ASTDT = as.Date(na_if(AESTDTC, "")), AENDT = as.Date(na_if(AEENDTC, "")),
         ASTDY = as.numeric(AESTDY), AENDY = as.numeric(AEENDY)) %>%
  left_join(SUBJ, by = "USUBJID") %>%
  mutate(
    # *** USE AESOC, NOT AEBODSYS: AEBODSYS is blank on every record here. ***
    AESOC   = if_else(is.na(AESOC) | AESOC == "", "(uncoded)", AESOC),
    AEDECOD = if_else(is.na(AEDECOD) | AEDECOD == "", AETERM, AEDECOD),
    ASEV    = factor(AESEV, levels = c("MILD", "MODERATE", "SEVERE")),
    ASEVN   = as.integer(ASEV),
    AREL    = AEREL,
    TRTEMFL = if_else(!is.na(ASTDT) & !is.na(TRTSDT) & ASTDT >= TRTSDT &
                        (is.na(TRTEDT) | ASTDT <= TRTEDT + 30), "Y", "N")
  )
if (all(ae$AEBODSYS == "" | is.na(ae$AEBODSYS)))
  cat("  CONFIRMED: AEBODSYS is blank on all", nrow(ae), "records -> AESOC used instead.\n")

# AOCC01FL: first occurrence of the MAXIMUM severity per subject per PT, so the
# by-max-severity table counts each subject once.
adae <- adae %>%
  group_by(USUBJID, AEDECOD) %>%
  arrange(desc(ASEVN), ASTDT, AESEQ, .by_group = TRUE) %>%
  mutate(AOCC01FL = if_else(row_number() == 1 & TRTEMFL == "Y", "Y", NA_character_)) %>%
  ungroup() %>%
  group_by(USUBJID) %>% arrange(ASTDT, AESEQ, .by_group = TRUE) %>%
  mutate(AOCCFL = if_else(row_number() == 1 & TRTEMFL == "Y", "Y", NA_character_)) %>%
  ungroup() %>%
  mutate(ASEV = as.character(ASEV)) %>%
  select(STUDYID, USUBJID, AESEQ, AETERM, AEDECOD, AESOC, AESOCCD, ASEV, ASEVN,
         AESER, AREL, AEACN, AEOUT, ASTDT, AENDT, ASTDY, AENDY,
         TRTEMFL, AOCC01FL, AOCCFL, TRTP, TRT01P, TRT01PN, TRT01A, SITEGR1, SAFFL)
cat(sprintf("  %d AE records; TRTEMFL=Y %d; AESER=Y %d; AEACN=DRUG WITHDRAWN %d; AEOUT=FATAL %d\n",
            nrow(adae), sum(adae$TRTEMFL == "Y"), sum(adae$AESER == "Y"),
            sum(adae$AEACN == "DRUG WITHDRAWN"), sum(adae$AEOUT == "FATAL")))
cat(sprintf("  reconciliation: distinct subjects with AEOUT=FATAL = %d vs ADSL DTHFL=Y = %d\n",
            n_distinct(adae$USUBJID[adae$AEOUT == "FATAL"]), sum(adsl$DTHFL == "Y", na.rm = TRUE)))
export_adam(adae, "ADAE")

# ================================================================== ADLB
cat("\n===== ADLB =====\n")
lb <- read_sdtm("LB")
QUAL <- c("ANISO", "COLOR", "KETONES", "MACROCY", "POIKILO", "UROBIL")
adlb <- lb %>%
  filter(!is.na(LBSTRESN), !LBTESTCD %in% QUAL) %>%
  transmute(STUDYID, USUBJID, PARAMCD = LBTESTCD, PARAM = LBTEST,
            PARCAT1 = LBCAT, AVAL = LBSTRESN, AVALU = LBSTRESU,
            ANRLO = LBSTNRLO, ANRHI = LBSTNRHI,
            ANRIND = na_if(LBNRIND, ""), SRCVISIT = VISIT,
            ADT = as.Date(substr(LBDTC, 1, 10)), DY = as.numeric(LBDY))
adlb <- window_by_day(adlb, "DY", FULL_T, FULL_VN) %>% filter(!is.na(AVISIT))
cat(sprintf("  RULE 1: %d records windowed; unscheduled source visits preserved: %s\n",
            nrow(adlb), paste(unique(grep("UNSCHEDULED", adlb$SRCVISIT, value = TRUE)), collapse = "; ")))
adlb <- adlb %>% derive_baseline() %>% flag_nearest() %>%
  add_locf(ENDPT_N, ENDPT_LAB, ENDPT_DAY) %>% add_anl02()
# baseline reference-range indicator
bnr <- adlb %>% filter(ABLFL == "Y") %>% distinct(USUBJID, PARAMCD, BNRIND = ANRIND)
adlb <- adlb %>% left_join(bnr, by = c("USUBJID", "PARAMCD"))
# WORSTFL: worst post-baseline reference-range indicator per subject x parameter.
# Worst direction = furthest from NORMAL; HIGH and LOW are both "abnormal".
adlb <- adlb %>%
  mutate(.abn = case_when(is.na(ANRIND) ~ 0L, ANRIND == "NORMAL" ~ 0L, TRUE ~ 1L)) %>%
  group_by(USUBJID, PARAMCD) %>%
  mutate(.pb = ADY > 1 & !is.na(ANRIND),
         .wrk = if_else(.pb, .abn * 1000 + coalesce(ADY, 0), NA_real_),
         WORSTFL = if_else(!is.na(.wrk) & .wrk == suppressWarnings(max(.wrk, na.rm = TRUE)) &
                             !duplicated(.wrk == suppressWarnings(max(.wrk, na.rm = TRUE)) & !is.na(.wrk)),
                           "Y", NA_character_)) %>%
  ungroup() %>% select(-.abn, -.pb, -.wrk)
# Hy's Law: ALT or AST >= 3xULN AND BILI >= 2xULN, evaluated per subject x visit.
hy <- adlb %>%
  filter(PARAMCD %in% c("ALT", "AST", "BILI"), !is.na(ANRHI), ANRHI > 0) %>%
  mutate(.x = AVAL / ANRHI) %>%
  select(USUBJID, AVISITN, PARAMCD, .x) %>%
  pivot_wider(names_from = PARAMCD, values_from = .x, values_fn = max) %>%
  mutate(.hy = (coalesce(ALT, 0) >= 3 | coalesce(AST, 0) >= 3) & coalesce(BILI, 0) >= 2) %>%
  filter(.hy) %>% distinct(USUBJID, AVISITN) %>% mutate(CRIT1FL = "Y")
adlb <- adlb %>% left_join(hy, by = c("USUBJID", "AVISITN")) %>%
  mutate(CRIT1 = "ALT or AST >= 3xULN AND BILI >= 2xULN",
         CRIT1FL = coalesce(CRIT1FL, "N"),
         # *** SD-4 (human review 2026-07-29): the clinically-significant-change
         # criterion is defined by neither the protocol nor any available SAP.
         # Derive as ALL-MISSING. Do NOT invent a threshold. T-14-6.03 must
         # footnote that the criterion is unspecified.
         CSCFL = NA_character_) %>%
  left_join(SUBJ, by = "USUBJID")
cat(sprintf("  Hy's Law: %d subject-visits meet CRIT1 (%d distinct subjects)\n",
            sum(adlb$CRIT1FL == "Y"), n_distinct(adlb$USUBJID[adlb$CRIT1FL == "Y"])))
cat("  SD-4: CSCFL derived as all-missing (criterion unspecified) per human review.\n")
export_adam(adlb, "ADLB")

# ================================================================== ADVS
cat("\n===== ADVS =====\n")
vs <- read_sdtm("VS")
# *** POSITION MUST BE IN PARAMCD *** SYSBP/DIABP/PULSE are each measured
# STANDING and SUPINE; collapsing across VSPOS would average two different
# measurements. USDM endpoint END4 names 'standing and supine blood pressure'.
POSSFX <- c(STANDING = "ST", SUPINE = "SU")
advs <- vs %>%
  filter(!is.na(VSSTRESN)) %>%
  mutate(.sfx = if_else(VSTESTCD %in% c("SYSBP", "DIABP", "PULSE"),
                        unname(POSSFX[VSPOS]), "")) %>%
  mutate(.sfx = coalesce(.sfx, "")) %>%
  transmute(STUDYID, USUBJID,
            PARAMCD = paste0(VSTESTCD, .sfx),
            PARAM = if_else(.sfx == "", VSTEST, paste0(VSTEST, ", ", str_to_title(VSPOS))),
            ATPT = na_if(VSPOS, ""), AVAL = VSSTRESN, AVALU = VSSTRESU,
            SRCVISIT = VISIT, ADT = as.Date(substr(VSDTC, 1, 10)), DY = as.numeric(VSDY))
advs <- window_by_day(advs, "DY", FULL_T, FULL_VN) %>% filter(!is.na(AVISIT)) %>%
  derive_baseline() %>% flag_nearest() %>%
  add_locf(ENDPT_N, ENDPT_LAB, ENDPT_DAY) %>% add_anl02() %>%
  left_join(SUBJ, by = "USUBJID")
cat("  PARAMCDs:", paste(sort(unique(advs$PARAMCD)), collapse = ", "), "\n")
export_adam(advs, "ADVS")

# ================================================================== ADEX
cat("\n===== ADEX =====\n")
ex <- read_sdtm("EX")
exs <- ex %>%
  mutate(STDT = as.Date(substr(EXSTDTC, 1, 10)), ENDT = as.Date(substr(EXENDTC, 1, 10))) %>%
  group_by(STUDYID, USUBJID) %>%
  summarise(TRTDUR  = as.numeric(max(ENDT, na.rm = TRUE) - min(STDT, na.rm = TRUE)) + 1,
            CUMDOSE = sum(EXDOSE, na.rm = TRUE), NDOSE = n(), .groups = "drop") %>%
  mutate(AVGDD = CUMDOSE / TRTDUR)
adex <- exs %>%
  pivot_longer(c(TRTDUR, CUMDOSE, AVGDD), names_to = "PARAMCD", values_to = "AVAL") %>%
  mutate(PARAM = recode(PARAMCD,
                        TRTDUR  = "Duration of Exposure (days)",
                        CUMDOSE = "Cumulative Dose (mg)",
                        AVGDD   = "Average Daily Dose (mg/day)")) %>%
  left_join(exs %>% select(USUBJID, TRTDUR), by = "USUBJID") %>%
  mutate(EXDURGR1 = case_when(TRTDUR <= 30 ~ "<=30 days", TRTDUR <= 90 ~ "31-90 days",
                              TRTDUR <= 168 ~ "91-168 days", TRUE ~ ">168 days")) %>%
  select(-TRTDUR) %>% left_join(SUBJ, by = "USUBJID")
cat(sprintf("  %d subjects with exposure; TRTDUR range %.0f-%.0f days\n",
            nrow(exs), min(exs$TRTDUR), max(exs$TRTDUR)))
export_adam(adex, "ADEX")

# ================================================================== ADCM
cat("\n===== ADCM =====\n")
cm <- read_sdtm("CM")
# *** NOT WHO-DD CODED: no CMDECOD / CMCLAS / CMATC in this extract. ***
adcm <- cm %>%
  transmute(STUDYID, USUBJID, CMSEQ, CMTRT, CMINDC, CMDOSE, CMDOSU, CMROUTE,
            ASTDT = safe_date(CMSTDTC, "CM CMSTDTC"), AENDT = safe_date(CMENDTC, "CM CMENDTC"),
            ASTDY = as.numeric(CMSTDY)) %>%
  group_by(USUBJID, CMTRT) %>% arrange(ASTDT, CMSEQ, .by_group = TRUE) %>%
  mutate(AOCCFL = if_else(row_number() == 1, "Y", NA_character_)) %>% ungroup() %>%
  left_join(SUBJ, by = "USUBJID")
# No WHO-DD class exists, so carry an explicit placeholder class rather than
# letting a downstream hierarchy silently collapse to nothing.
adcm$CMCLASX <- "(uncoded - no WHO-DD therapeutic class in source)"
cat(sprintf("  %d records, %d subjects, %d distinct verbatim terms. CMDECOD absent -> verbatim only.\n",
            nrow(adcm), n_distinct(adcm$USUBJID), n_distinct(adcm$CMTRT)))
export_adam(adcm, "ADCM")

# ================================================================== ADMH
cat("\n===== ADMH =====\n")
mh <- read_sdtm("MH")
# MH is UNCODED here (MHTERM only, no MHDECOD/MHBODSYS). A real ADaM would carry
# a coded SOC; we carry an explicit placeholder so the display states the gap.
admh <- mh %>%
  transmute(STUDYID, USUBJID, MHSEQ, MHTERM,
            MHDECOD = MHTERM, MHBODSYS = "(uncoded - no MedDRA SOC in source)",
            ASTDT = safe_date(MHSTDTC, "MH MHSTDTC"), ASTDY = as.numeric(MHSTDY)) %>%
  left_join(SUBJ, by = "USUBJID") %>%
  filter(ITTFL == "Y")
cat(sprintf("  %d records, %d subjects, %d distinct terms (uncoded).\n",
            nrow(admh), n_distinct(admh$USUBJID), n_distinct(admh$MHTERM)))
export_adam(admh, "ADMH")

# ================================================================== ADTTE
cat("\n===== ADTTE =====\n")
fa <- read_sdtm("FA")
# Time to first injection-site reaction: earliest FADY with an occurrence of Y
# in FACAT 'INJECTION SITE REACTION'.
isr <- fa %>%
  filter(FACAT == "INJECTION SITE REACTION", FATESTCD == "OCCUR", FASTRESC == "Y") %>%
  group_by(USUBJID) %>% summarise(EVDY = min(FADY, na.rm = TRUE), .groups = "drop")
risk <- adsl %>% filter(SAFFL == "Y") %>%
  transmute(STUDYID, USUBJID, TRTSDT = as.Date(TRTSDT), TRTEDT = as.Date(TRTEDT))
adtte <- risk %>%
  left_join(isr, by = "USUBJID") %>%
  mutate(PARAMCD = "TTISR", PARAM = "Time to First Injection-Site Reaction (days)",
         CNSR = if_else(is.na(EVDY), 1L, 0L),
         AVAL = if_else(is.na(EVDY), as.numeric(TRTEDT - TRTSDT) + 1, as.numeric(EVDY)),
         STARTDT = TRTSDT,
         ADT = if_else(is.na(EVDY), TRTEDT, TRTSDT + (EVDY - 1)),
         EVNTDESC = if_else(CNSR == 0, "First injection-site reaction", NA_character_),
         CNSDTDSC = if_else(CNSR == 1, "Last day on study drug", NA_character_)) %>%
  select(-EVDY, -TRTEDT) %>%
  left_join(SUBJ %>% select(-TRTSDT, -TRTEDT), by = "USUBJID")
cat(sprintf("  %d subjects at risk; %d events, %d censored\n",
            nrow(adtte), sum(adtte$CNSR == 0), sum(adtte$CNSR == 1)))
cat(sprintf("  DATA LIMITATION: FA was collected on only %d of %d safety subjects; subjects\n",
            n_distinct(fa$USUBJID), nrow(risk)),
    "  with no FA record are censored, which understates the event rate. Footnote required.\n", sep = "")
export_adam(adtte, "ADTTE")

cat("\n03_safety.R complete\n")
