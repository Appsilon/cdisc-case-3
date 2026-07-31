# Name: 02_efficacy_bds.R
# Description: Generate ADQSPHQ, ADQSSWL, ADFTAVLT, ADRSHAMD
#              — satisfies adam-spec.json datasets of the same names.
# Supports tables: 14-3.01 .02 .03 .04 .05, 14-2.02
# Implements MANDATORY RULE 1 (day-based windowing) and RULE 2 (LOCF endpoint).
# ----------------------------------------------------------------------------
source("00_setup.R")

adsl <- read_adam("ADSL")
SUBJ <- adsl %>% select(USUBJID, TRTP, TRT01P, TRT01PN, SITEGR1, ITTFL, SAFFL, EFFFL, COMPLFL)

ENDPT_N <- 24; ENDPT_LAB <- "Week 24"; ENDPT_DAY <- 169

finish <- function(df) {
  df %>% left_join(SUBJ, by = "USUBJID") %>%
    arrange(USUBJID, PARAMCD, AVISITN, ADY) %>%
    as.data.frame()
}

# ============================================================ ADQSPHQ (PHQ-9)
cat("\n===== ADQSPHQ =====\n")
qsph <- read_sdtm("QSPH")
# PHQ-9 total is supplied as QSTESTCD 'PHQ0111'; do NOT sum the 10 items.
phq <- qsph %>%
  filter(QSTESTCD == "PHQ0111", !is.na(QSSTRESN)) %>%
  transmute(STUDYID, USUBJID, PARAMCD = "PHQTOT", PARAM = "PHQ-9 Total Score",
            PARAMN = 1, AVAL = QSSTRESN, SRCVISIT = VISIT, ADT = as.Date(QSDTC), DY = QSDY)
# PHQ-9 is collected at Baseline, Week 12, 16, 20, 24 only -> window onto THAT set.
PHQ_T  <- c("Baseline" = 1, "Week 12" = 85, "Week 16" = 113, "Week 20" = 141, "Week 24" = 169)
PHQ_VN <- c("Baseline" = 0, "Week 12" = 12, "Week 16" = 16, "Week 20" = 20, "Week 24" = 24)
phq <- window_by_day(phq, "DY", PHQ_T, PHQ_VN) %>% filter(!is.na(AVISIT))
cat("  RULE 1 windowing (source visit -> analysis visit):\n")
print(table(phq$SRCVISIT, phq$AVISIT))
phq <- phq %>% derive_baseline() %>% flag_nearest() %>%
  add_locf(ENDPT_N, ENDPT_LAB, ENDPT_DAY) %>% add_anl02() %>% finish()
export_adam(phq, "ADQSPHQ")

# ============================================================ ADQSSWL (SWLS)
cat("\n===== ADQSSWL =====\n")
qssl <- read_sdtm("QSSL")
# *** SD-1: SDTM carries NO SWLS total-score record. Derive it as the sum of the
# 5 items, MISSING unless all 5 items are present at that visit. NITEMS is kept
# so a reviewer can verify the completeness rule was applied.
swl <- qssl %>%
  filter(grepl("^SWLS01", QSTESTCD), !is.na(QSSTRESN)) %>%
  group_by(STUDYID, USUBJID, VISIT, QSDTC, QSDY) %>%
  summarise(NITEMS = n(), .sum = sum(QSSTRESN), .groups = "drop") %>%
  transmute(STUDYID, USUBJID, PARAMCD = "SWLSTOT",
            PARAM = "Satisfaction With Life Scale Total Score", PARAMN = 1,
            NITEMS, AVAL = if_else(NITEMS == 5, .sum, NA_real_),
            SRCVISIT = VISIT, ADT = as.Date(QSDTC), DY = QSDY) %>%
  filter(!is.na(AVAL))
cat(sprintf("  SD-1: SWLSTOT derived from 5 items; %d visit-level totals, all with NITEMS=5\n",
            nrow(swl)))
swl <- window_by_day(swl, "DY", PHQ_T, PHQ_VN) %>% filter(!is.na(AVISIT))
cat("  RULE 1 windowing:\n"); print(table(swl$SRCVISIT, swl$AVISIT))
swl <- swl %>% derive_baseline() %>% flag_nearest() %>%
  add_locf(ENDPT_N, ENDPT_LAB, ENDPT_DAY) %>% add_anl02() %>% finish()
export_adam(swl, "ADQSSWL")

# ============================================================ ADFTAVLT
cat("\n===== ADFTAVLT =====\n")
ft <- read_sdtm("FT")
# *** SD-7 (discovered at derivation, corrects adam-spec.json) ***
# 'AVL02-List A Total' is NOT one score per visit: AVLT-REY administers List A
# seven times (FTREPNUM 1-7). Trials 1-5 are the learning trials, 6 is recall
# after interference, 7 (FTTPT '30 MIN POST') is delayed recall. Taking a single
# FTREPNUM record — which the generic nearest-day flag would have done silently —
# would analyse one arbitrary trial instead of the instrument's score.
# Standard scoring:
#   AVLATOT = SUM of trials 1-5  (Total Learning; the conventional AVLT endpoint)
#   AVLADEL = trial 7            (30-minute delayed recall)
avl_raw <- ft %>% filter(FTTESTCD == "AVL0216", !is.na(FTSTRESN))
# NOTE: FTDTC carries a TIME component (12:00, 12:05, ... one per trial), so it
# must NOT be part of the grouping key — grouping on the datetime would leave
# each trial in its own group and silently produce no totals at all.
avl_tot <- avl_raw %>%
  filter(FTREPNUM %in% 1:5) %>%
  group_by(STUDYID, USUBJID, VISIT, FTDY) %>%
  summarise(NTRIALS = n(), .sum = sum(FTSTRESN),
            .dtc = min(FTDTC), .groups = "drop") %>%
  transmute(STUDYID, USUBJID, PARAMCD = "AVLATOT",
            PARAM = "AVLT-REY List A Total Learning (sum of trials 1-5)", PARAMN = 1,
            NTRIALS, AVAL = if_else(NTRIALS == 5, .sum, NA_real_),
            SRCVISIT = VISIT, ADT = as.Date(substr(.dtc, 1, 10)), DY = FTDY)
avl_del <- avl_raw %>%
  filter(FTREPNUM == 7) %>%
  transmute(STUDYID, USUBJID, PARAMCD = "AVLADEL",
            PARAM = "AVLT-REY List A 30-Minute Delayed Recall", PARAMN = 2,
            NTRIALS = 1L, AVAL = FTSTRESN, SRCVISIT = VISIT,
            ADT = as.Date(substr(FTDTC,1,10)), DY = FTDY)
avl <- bind_rows(avl_tot, avl_del) %>% filter(!is.na(AVAL))
cat(sprintf("  SD-7: AVLATOT = sum of trials 1-5 (%d visit-level scores); AVLADEL = trial 7 (%d)\n",
            nrow(avl_tot), nrow(avl_del)))
# *** SD-2: AVLT-REY has NO 'BASELINE' visit. Its earliest assessment is
# SCREENING 2 at study day -2/-1, so the baseline cutoff is widened to ADY <= 1
# (which captures SCREENING 2) and the baseline record is that screening visit.
AVL_T  <- c("Baseline" = -1, "Week 4" = 29, "Week 8" = 57, "Week 12" = 85,
            "Week 16" = 113, "Week 24" = 169)
AVL_VN <- c("Baseline" = 0, "Week 4" = 4, "Week 8" = 8, "Week 12" = 12,
            "Week 16" = 16, "Week 24" = 24)
avl <- window_by_day(avl, "DY", AVL_T, AVL_VN) %>% filter(!is.na(AVISIT))
cat("  RULE 1 windowing (SD-2: SCREENING 2 serves as baseline):\n")
print(table(avl$SRCVISIT, avl$AVISIT))
avl <- avl %>% derive_baseline(bl_cutoff = 1) %>% flag_nearest() %>%
  add_locf(ENDPT_N, ENDPT_LAB, ENDPT_DAY) %>% add_anl02() %>% finish()
export_adam(avl, "ADFTAVLT")

# ============================================================ ADRSHAMD
cat("\n===== ADRSHAMD =====\n")
rs <- read_sdtm("RS")
# *** SD-3 CORRECTED at derivation ***
# The spec asserted "no post-baseline data, so BASE/CHG/LOCF are not derivable".
# That is wrong. HAMD 17 has no *scheduled* post-baseline visit, but the EARLY
# DISCONTINUATION RETRIEVAL records fall at study days 167-173 — inside the
# Week-24 window — and 6 subjects have BOTH a baseline and an ED record. A
# change-from-baseline analysis at Week 24 IS therefore derivable (n=6).
# This is precisely the failure mode MANDATORY RULE 1 exists to prevent: reading
# the nominal visit list alone hid real post-baseline data.
# BASE/CHG and the LOCF endpoint record are derived below. The consuming display
# T-14-2.02 remains a baseline summary in section 14-2 per the reviewed plan; the
# derived CHG is reported as an available-but-unused analysis in issues.md.
ham <- rs %>%
  filter(RSTESTCD == "HAMD118", !is.na(RSSTRESN)) %>%
  transmute(STUDYID, USUBJID, PARAMCD = "HAMD118", PARAM = "HAMD 17 Total Score",
            PARAMN = 1, AVAL = RSSTRESN, SRCVISIT = VISIT,
            ADT = as.Date(RSDTC), DY = RSDY)
HAM_T  <- c("Baseline" = 1, "Week 24" = 169)
HAM_VN <- c("Baseline" = 0, "Week 24" = 24)
ham <- window_by_day(ham, "DY", HAM_T, HAM_VN) %>% filter(!is.na(AVISIT))
cat("  RULE 1 windowing:\n"); print(table(ham$SRCVISIT, ham$AVISIT))
ham <- ham %>% derive_baseline() %>% flag_nearest() %>%
  add_locf(ENDPT_N, ENDPT_LAB, ENDPT_DAY) %>% add_anl02() %>% finish()
cat(sprintf("  SD-3 corrected: %d subjects have baseline + a Week-24-window record => CHG derivable.\n",
            sum(ham$AVISITN == 24 & ham$ANL01FL == "Y" & !is.na(ham$CHG), na.rm = TRUE)))
export_adam(ham, "ADRSHAMD")

cat("\n02_efficacy_bds.R complete\n")
