# ADaM Derivation Plan — CDISCPILOT01

Spec-driven from `outputs/tlf-plan/adam-spec.json`. SDTM source: `inputs/sdtm/`.
Output: `outputs/adam/data/` (CSV + JSON), code in `outputs/adam/code/`.

## SDTM inventory

| Domain | Records | Variables | Used by |
|---|---|---|---|
| AE | 74 | 37 | ADAE, ADTTE |
| CM | 68 | 17 | ADCM |
| DD | 3 | 12 | ADSL |
| DI | 34 | 7 | (not required) |
| DM | 18 | 26 | ADSL |
| DS | 53 | 12 | ADSL |
| EC | 1590 | 21 | ADEX (cross-check) |
| EX | 1583 | 17 | ADSL, ADEX |
| FA | 78 | 16 | ADTTE |
| FT | 4488 | 22 | ADFTAVLT |
| IE | 1 | 12 | (not required) |
| LB | 3488 | 23 | ADLB |
| MH | 17 | 8 | (T-14-1.04, read directly) |
| OE | 285 | 18 | (no planned output) |
| QSPH | 330 | 17 | ADQSPHQ |
| QSSL | 135 | 16 | ADQSSWL |
| RELREC | 6 | 7 | (not required) |
| RS | 375 | 17 | ADRSHAMD |
| SE | 43 | 11 | (not required) |
| SUPPDM | 3 | 10 | (race detail, not required) |
| SUPPEC | 7 | 10 | (not required) |
| SV | 164 | 10 | (not required) |
| TA | 8 | 10 | (not required) |
| TE | 5 | 6 | (not required) |
| TI | 62 | 6 | (not required) |
| TS | 51 | 11 | (study metadata / objectives) |
| TV | 14 | 7 | (not required) |
| VS | 1414 | 21 | ADSL, ADVS |

**Absent and relevant:** `DV` (protocol deviations) — the deviations table stays blocked.

## ADSL — ADSL — supports 14-1, 14-1.01, 14-1.02, 14-1.03, 14-1.04, 14-2.01, 14-2.02, 14-3.01, 14-3.02, 14-3.03, 14-3.04, 14-3.05, 14-4.01, 14-5.01, 14-5.02, 14-5.03, 14-5.04, 14-5.05, 14-5.06, 14-6.01, 14-6.02, 14-6.03, 14-6.04, 14-6.05, 14-6.06, 14-7.01, 14-7.02, 14-7.03, 14-7.04

- **Source SDTM**: DM, DS, EX, SV, SUPPDM, DD (all present)
- **Derived**: 18 rows x 40 columns
- **Mandatory rules applied**: SITEGR1 pooling counts RANDOMIZED (ITTFL='Y') subjects
- **Notes / gaps**:
  - 18 DM records: 17 randomized + 1 screen failure (blank ARM). RANDFL/ITTFL must exclude the screen failure.
  - ACTARM equals ARM for every subject in this extract — no as-treated deviations.
  - DTHCAUS requires a join to SDTM DD (3 records).
  - Conformance correction (metatools::check_variables, 2026-07-29): ARMCD, ACTARMCD, TRTP, AGEU and AGEGR1N were derived but not enumerated in this spec. TRTP in particular is the grouping variable every analysis-spec entry references, so its omission was a real spec defect. Added.

## ADQSPHQ — BDS — supports 14-3.01, 14-3.04, 14-3.05

- **Source SDTM**: QSPH (all present)
- **Derived**: 32 rows x 28 columns
- **Parameters**:
  - `PHQTOT` — PHQ-9 Total Score *(Use the pre-computed total record. Do NOT sum PHQ0101..PHQ0110 — the total is supplied. Range 0-27.)*
- **Mandatory rules applied**: Day-based analysis-visit windowing that never drops unscheduled/ET visits; LOCF record creation at the endpoint visit
- **Week-24 endpoint records**: 10 (8 observed, 2 LOCF)
- **Notes / gaps**:
  - Endpoint visit = Week 24 (AVISITN 24). Observed coverage: 13 BASELINE, 2 WEEK 24, 6 EARLY DISCONTINUATION RETRIEVAL, plus WEEK 12/16/20.
  - The ED RETRIEVAL record must be windowed by ADY, not dropped — it is the source of most LOCF values.

## ADQSSWL — BDS — supports 14-3.02

- **Source SDTM**: QSSL (all present)
- **Derived**: 28 rows x 29 columns
- **Parameters**:
  - `SWLSTOT` — Satisfaction With Life Scale Total Score *(*** NO TOTAL-SCORE RECORD EXISTS IN SDTM *** Derive as the sum of the 5 items. Completeness rule: set the total to MISSING unless all 5 items are non-missing at that visit. Document the rule in define.xml.)*
- **Mandatory rules applied**: Day-based analysis-visit windowing that never drops unscheduled/ET visits; LOCF record creation at the endpoint visit
- **Week-24 endpoint records**: 9 (8 observed, 1 LOCF)
- **Notes / gaps**:
  - Same visit sparsity as PHQ-9: 13 subjects at BASELINE, 2 at WEEK 24, 6 with ED RETRIEVAL.
  - NITEMS is carried so a reviewer can verify the completeness rule was applied.

## ADFTAVLT — BDS — supports 14-3.03

- **Source SDTM**: FT (all present)
- **Derived**: 78 rows x 29 columns
- **Parameters**:
  - `AVLATOT` — AVLT-REY List A Total Learning (sum of trials 1-5) *(SD-7. 'AVL02-List A Total' is scored PER TRIAL (FTREPNUM 1-7), not once per visit. Trials 1-5 are the learning trials; their sum is the conventional AVLT Total Learning endpoint. Completeness rule: missing unless all 5 trials are present. CAUTION: FTDTC carries a time component (one per trial) and must NOT be part of the aggregation key.)*
  - `AVLADEL` — AVLT-REY List A 30-Minute Delayed Recall *(SD-7. Derived and retained; not consumed by a planned table.)*
- **Mandatory rules applied**: Day-based analysis-visit windowing that never drops unscheduled/ET visits; LOCF record creation at the endpoint visit
- **Week-24 endpoint records**: 22 (10 observed, 12 LOCF)
- **Notes / gaps**:
  - *** BASELINE DEVIATION *** FT has NO 'BASELINE' visit for AVLT-REY. The earliest assessment is SCREENING 2 (98 records). ABLFL MUST be set on the SCREENING 2 record; FTLOBXFL='Y' should corroborate. Document the deviation in define.xml and footnote every consuming table.
  - Best-populated efficacy endpoint: 14 observed WEEK 24 records and 21 ED RETRIEVAL records.
  - SD-7 (discovered at derivation): the original spec treated 'AVL02-List A Total' as one score per visit. It is one score per trial. Taking a single FTREPNUM record would have analysed an arbitrary learning trial instead of the instrument's score. Parameters corrected above.

## ADRSHAMD — BDS — supports 14-2.02

- **Source SDTM**: RS (all present)
- **Derived**: 21 rows x 28 columns
- **Parameters**:
  - `HAMD118` — HAMD 17 Total Score *(RSCAT='HAMD 17'.)*
- **Mandatory rules applied**: Day-based analysis-visit windowing that never drops unscheduled/ET visits
- **Week-24 endpoint records**: 7 (7 observed, 0 LOCF)
- **Notes / gaps**:
  - *** NO POST-BASELINE DATA *** RS collects HAMD 17 only at BASELINE and EARLY DISCONTINUATION RETRIEVAL. There are no scheduled post-baseline visits, so BASE/CHG/LOCF are NOT derivable and MANDATORY-2 does not apply. Baseline records only; consumed by the §14-2 baseline table T-14-2.02.

## ADAE — OCCDS — supports 14-1, 14-5.01, 14-5.02, 14-5.03, 14-5.04, 14-5.05, 14-5.06

- **Source SDTM**: AE (all present)
- **Derived**: 74 rows x 26 columns
- **Mandatory rules applied**: none (not a windowed BDS dataset)
- **Notes / gaps**:
  - 74 AE records. AESER='Y' on 4; AEACN='DRUG WITHDRAWN' present; AEOUT='FATAL' present.
  - Reconcile AEOUT='FATAL' subject count against ADSL.DTHFL (3) and report any mismatch.

## ADLB — BDS — supports 14-6.01, 14-6.02, 14-6.03, 14-6.04, 14-6.05, 14-6.06

- **Source SDTM**: LB (all present)
- **Derived**: 3706 rows x 41 columns
- **Parameters**:
  - `<LBTESTCD>` — <LBTEST> *(CHEMISTRY: ALB ALP ALT AST BILI CA CHOL CK CL CREAT GGT GLUC K PHOS PROT SODIUM TSH URATE UREAN VITB12. HEMATOLOGY: BASO EOS HCT HGB LYM MCH MCHC MCV MONO PLAT RBC WBC. URINALYSIS: PH SPGRAV UROBIL. OTHER (QUALITATIVE, EXCLUDE from continuous summaries): ANISO COLOR KETONES MACROCY POIKILO.)*
  - `ALT/AST/BILI/ALP` — Hy's Law components *(All four present — the criterion is derivable.)*
- **Mandatory rules applied**: Day-based analysis-visit windowing that never drops unscheduled/ET visits; LOCF record creation at the endpoint visit
- **Week-24 endpoint records**: 480 (96 observed, 384 LOCF)
- **Notes / gaps**:
  - 3488 records. LB is the domain with explicit unscheduled visits — MANDATORY-1 is load-bearing here.
  - Restrict continuous summaries to parameters with a numeric LBSTRESN.

## ADVS — BDS — supports 14-7.01, 14-7.02, 14-7.03

- **Source SDTM**: VS (all present)
- **Derived**: 1458 rows x 33 columns
- **Parameters**:
  - `SYSBPST` — Systolic Blood Pressure, Standing
  - `SYSBPSU` — Systolic Blood Pressure, Supine
  - `DIABPST` — Diastolic Blood Pressure, Standing
  - `DIABPSU` — Diastolic Blood Pressure, Supine
  - `PULSEST` — Pulse Rate, Standing
  - `PULSESU` — Pulse Rate, Supine
  - `TEMP` — Temperature
  - `WEIGHT` — Weight
  - `HEIGHT` — Height *(Baseline only; feeds ADSL.HEIGHTBL/BMIBL, not a safety table.)*
- **Mandatory rules applied**: Day-based analysis-visit windowing that never drops unscheduled/ET visits; LOCF record creation at the endpoint visit
- **Week-24 endpoint records**: 117 (73 observed, 44 LOCF)
- **Notes / gaps**:
  - *** POSITION MUST BE IN PARAMCD *** SYSBP/DIABP/PULSE are each measured STANDING and SUPINE. Collapsing across VSPOS would average two different measurements. USDM endpoint END4 explicitly names 'standing and supine blood pressure'.
  - 1414 records across SCREENING 1 .. WEEK 26 plus EARLY DISCONTINUATION RETRIEVAL.

## ADEX — BDS — supports 14-4.01

- **Source SDTM**: EX, EC (all present)
- **Derived**: 51 rows x 19 columns
- **Parameters**:
  - `TRTDUR` — Duration of Exposure (days) *(last EXENDT - first EXSTDT + 1)*
  - `CUMDOSE` — Cumulative Dose (mg) *(sum of EXDOSE over all exposure records)*
  - `AVGDD` — Average Daily Dose (mg/day) *(CUMDOSE / TRTDUR)*
- **Mandatory rules applied**: none (not a windowed BDS dataset)
- **Notes / gaps**:
  - EX has 1583 records (EXTRT ZANOMALINE / PLACEBO). EC (1590 records, as-collected) is retained as a cross-check on ECOCCUR but EX is the derivation source.

## ADCM — OCCDS — supports 14-7.04

- **Source SDTM**: CM (all present)
- **Derived**: 68 rows x 24 columns
- **Mandatory rules applied**: none (not a windowed BDS dataset)
- **Notes / gaps**:
  - *** NOT WHO-DD CODED *** No CMDECOD, no CMCLAS/CMATC in this extract. The conventional therapeutic-class hierarchy is NOT derivable; T-14-7.04 must summarize verbatim CMTRT and footnote the absence of coding. 68 records across 14 subjects.

## ADTTE — TTE — supports 14-1

- **Source SDTM**: FA, AE, DM, EX (all present)
- **Derived**: 17 rows x 21 columns
- **Parameters**:
  - `TTISR` — Time to First Injection-Site Reaction *(AVAL = first FADTC with an occurrence result, minus TRTSDT, +1. Subjects with no reaction are censored (CNSR=1) at their last on-study day.)*
- **Mandatory rules applied**: none (not a windowed BDS dataset)
- **Notes / gaps**:
  - The USDM endpoint END3 describes a transdermal APPLICATION-site signal; the delivered study is a SUBCUTANEOUS INJECTION with an FA domain of category 'INJECTION SITE REACTION'. Derivation follows the delivered route; record as a reporting deviation.
  - FA carries FATESTCD 'Occurrence Indicator' and 'Severity/Intensity' with FAOBJ naming the reaction.

