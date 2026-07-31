# Data-Quality Gate — CDISCPILOT01 ADaM

Run: spec-driven from `outputs/tlf-plan/adam-spec.json`. Error-severity failures: **0**.

The gate asserts **derivation correctness** (did we lose records? did LOCF run?), not
statistical adequacy. With 17 randomized subjects this study cannot meet a conventional
N threshold and every inferential result downstream is illustrative only.

| ID | Check | Actual | Expected | Severity | Status |
|---|---|---|---|---|---|
| NG-1 | ADSL total records | 18 | 18 | error | PASS |
| NG-1b | ADSL ITTFL='Y' | 17 | 17 | error | PASS |
| NG-2 | ITT N by arm (Placebo/High/Low) | 5, 7, 5 | 5, 7, 5 | error | PASS |
| NG-3 | ADSL SAFFL='Y' == ITTFL='Y' | 17 | 17 | warning | PASS |
| NG-6 | distinct SITEGR1 groups (randomized) | 1 | 1 | warning | PASS |
| NG-4/ADQSPHQ | PHQTOT eligible subjects dropped from endpoint | 0 | 0 | error | PASS |
| NG-7/ADQSPHQ | duplicate ANL01FL primary records at endpoint | 0 | 0 | error | PASS |
| NG-4/ADQSSWL | SWLSTOT eligible subjects dropped from endpoint | 0 | 0 | error | PASS |
| NG-7/ADQSSWL | duplicate ANL01FL primary records at endpoint | 0 | 0 | error | PASS |
| NG-4/ADFTAVLT | AVLATOT eligible subjects dropped from endpoint | 0 | 0 | error | PASS |
| NG-7/ADFTAVLT | duplicate ANL01FL primary records at endpoint | 0 | 0 | error | PASS |
| NG-4/ADRSHAMD | HAMD118 eligible subjects dropped from endpoint | 0 | 0 | error | PASS |
| NG-7/ADRSHAMD | duplicate ANL01FL primary records at endpoint | 0 | 0 | error | PASS |
| NG-5/ADLB | observed analysis records vs source records | 3322 | 3322 | error | PASS |
| NG-5/ADVS | observed analysis records vs source records | 1414 | 1414 | error | PASS |
| NG-5b | PHQ-9 early-discontinuation records retained | 6 | 6 | error | PASS |
| NG-5c | ADLB unscheduled-visit records retained | TRUE | TRUE | error | PASS |
| NG-8 | distinct subjects AEOUT=FATAL vs ADSL DTHFL=Y | 3 | 3 | warning | PASS |

## Notes

- **NG-1** — 18 DM records = 17 randomized + 1 screen failure (CDISC015).
- **NG-1b** — Screen failure correctly excluded from ITT.
- **NG-3** — All randomized subjects were dosed.
- **NG-6** — Rule 3 applied on randomized counts. 17 subjects over 6 sites and 3 arms means no site reaches 3 randomized subjects in every arm, so all pool to 900. SITEGR1 is single-level and rank-deficient as an ANCOVA covariate -> the generator must refit without it. This is the rule working, not a defect.
- **NG-4/ADQSPHQ** — Shortfall test of MANDATORY RULE 2. endpoint N=10 (observed 8, LOCF 2); eligible (baseline + post-baseline) = 10; 0 endpoint record(s) have no baseline so contribute no CHG.
- **NG-4/ADQSSWL** — Shortfall test of MANDATORY RULE 2. endpoint N=9 (observed 8, LOCF 1); eligible (baseline + post-baseline) = 9; 0 endpoint record(s) have no baseline so contribute no CHG.
- **NG-4/ADFTAVLT** — Shortfall test of MANDATORY RULE 2. endpoint N=11 (observed 5, LOCF 6); eligible (baseline + post-baseline) = 10; 1 endpoint record(s) have no baseline so contribute no CHG.
- **NG-4/ADRSHAMD** — Shortfall test of MANDATORY RULE 2. endpoint N=7 (observed 7, LOCF 0); eligible (baseline + post-baseline) = 6; 1 endpoint record(s) have no baseline so contribute no CHG.
- **NG-5/ADLB** — Any shortfall means windowing dropped source records.
- **NG-5/ADVS** — Any shortfall means windowing dropped source records.
- **NG-5b** — These 6 records fall at study days 169-173 and window to Week 24. A nominal-VISITNUM map would drop them.
- **NG-8** — Source-data consistency check, not a derivation check.
