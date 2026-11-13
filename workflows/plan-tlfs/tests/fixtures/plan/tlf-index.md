# TLF Plan — CDISCPILOT01 (CDISC PILOT - LZZT)

*Safety and Efficacy of the Xanomeline Transdermal Therapeutic System (TTS) in Patients with Mild to Moderate Alzheimer's* — Phase II, parallel, double-blind, placebo-controlled, 3 arms.

Source: `inputs/usdm.json` (USDM v4.0.0) · Feasibility checked against `inputs/sdtm/` · No SAP supplied (variant Mode B — conventional defaults).

**Producible: 30 (28 tables, 1 figure, 1 listing). Blocked: 17. Needs clarification: 3. Total candidates: 50.**

> ## ⚠ Blocking finding — the USDM and the delivered SDTM are different studies
>
> `inputs/usdm.json` defines **xanomeline TTS** (transdermal) with **ADAS-Cog (11)/(14), CIBIC+, NPI-X and DAD**
> as the efficacy instruments. `inputs/sdtm/` carries `STUDYID='CDISCPILOT01'` but is the CDISC SDTM-MSG
> **Zanomaline** sample study: subcutaneous injection, **18 subjects** (17 randomized: Placebo 5 / Low 5 / High 7),
> and the instruments actually collected are **PHQ-9, SWLS, HAMD 17 and AVLT-REY**. **None** of the USDM efficacy
> instruments exist in the data. (`TS.TITLE='…Zanomaline…'`, `TS.ROUTE='SUBCUTANEOUS'`, `TS.REGID='NCT00000000'`.)
>
> **Human review decision (2026-07-29): the delivered data defines this study's efficacy.** Accordingly:
>
> * Safety, exposure, disposition and demographics domains (AE, LB, VS, CM, EX, DS, DM, MH, DD) align with the USDM → `planned`.
> * **All 13 USDM-derived efficacy candidates (ADAS-Cog / CIBIC+ / NPI-X) remain `blocked`** and are retained below for audit.
> * The **data-aligned efficacy block** (PHQ-9 / SWLS / AVLT-REY / HAMD 17) is **promoted to `planned`** and occupies §14-3.
>   Its provenance is the SDTM `TS` `OBJPRIM`/`OUTMSPRI` declaration, **not** a USDM objective/endpoint — this is a
>   known, deliberate traceability break, recorded on every affected candidate.
> * At N=17 randomized, **every inferential statistic in this run is illustrative, not interpretable.**
>   Only 2 subjects have an observed Week-24 PHQ-9/SWLS record, so those endpoints are produced almost entirely by the
>   mandatory LOCF rule (expected analysis n ≈ 13). All sex-subgroup and observed-cases variants are N-gate blocked.


## 14-1 — Subject Disposition / Populations

| ID | Type | Title | Population / Method | Traces-to | Status |
|---|---|---|---|---|---|
| T-14-1.01 | Table | Summary of Populations | All Subjects / Descriptive | ICH E3 §11.1 | planned |
| T-14-1.02 | Table | Summary of End of Study Data | Intent-to-Treat / Descriptive | ICH E3 §10.1 | planned |
| T-14-1.03 | Table | Summary of Number of Subjects by Site | All Subjects / Descriptive | ICH E3 §10.1 | planned |
| T-14-1.04 | Table | Summary of Medical History | Intent-to-Treat / Incidence | ICH E3 §11.2 | planned |

## 14-2 — Demographics & Baseline Characteristics

| ID | Type | Title | Population / Method | Traces-to | Status |
|---|---|---|---|---|---|
| T-14-2.01 | Table | Summary of Demographic and Baseline Characteristics | Intent-to-Treat / Descriptive | ICH E3 §11.2 | planned |
| T-14-2.02 | Table | Summary of HAMD 17 Total Score at Baseline | Intent-to-Treat / Descriptive | OBJTS1 / ENDTS2 | planned |

## 14-3 — Efficacy Analyses

| ID | Type | Title | Population / Method | Traces-to | Status |
|---|---|---|---|---|---|
| T-14-3.01 | Table | Change from Baseline to Week 24 in PHQ-9 Total Score - LOCF | Efficacy / ANCOVA / LOCF | OBJTS1 / ENDTS1 | planned |
| T-14-3.02 | Table | Change from Baseline to Week 24 in Satisfaction With Life Scale (SWLS) Total Score - LOCF | Efficacy / ANCOVA / LOCF | OBJTS2 / ENDTS3 | planned |
| T-14-3.03 | Table | Change from Baseline to Week 24 in AVLT-REY List A Total Score - LOCF | Efficacy / ANCOVA / LOCF | OBJTS3 / ENDTS4 | planned |
| T-14-3.04 | Table | Repeated Measures Analysis of Change from Baseline to Week 24 in PHQ-9 Total Score | Efficacy / MMRM | OBJTS1 / ENDTS1 | planned |
| T-14-3.05 | Table | PHQ-9 Total Score - Mean and Mean Change from Baseline Over Time | Efficacy / Descriptive | OBJTS1 / ENDTS1 | planned |

## 14-4 — Drug Exposure

| ID | Type | Title | Population / Method | Traces-to | Status |
|---|---|---|---|---|---|
| T-14-4.01 | Table | Summary of Planned Exposure to Study Drug | Safety / Descriptive | ICH E3 §12.1 | planned |

## 14-5 — Adverse Events

| ID | Type | Title | Population / Method | Traces-to | Status |
|---|---|---|---|---|---|
| L-14-5.01 | Listing | Listing of Deaths | Safety / none | ICH E3 §12.3 | planned |
| T-14-5.01 | Table | Incidence of Treatment-Emergent Adverse Events by System Organ Class and Preferred Term | Safety / Incidence | OBJ2 / END3 | planned |
| T-14-5.02 | Table | Incidence of Treatment-Emergent Serious Adverse Events by System Organ Class and Preferred Term | Safety / Incidence | OBJ2 / END3 | planned |
| T-14-5.03 | Table | Incidence of Adverse Events Leading to Study Drug Discontinuation | Safety / Incidence | OBJ2 / END3 | planned |
| T-14-5.04 | Table | Incidence of Adverse Events with a Fatal Outcome (Deaths) | Safety / Incidence | OBJ2 / END3 | planned |
| T-14-5.05 | Table | Incidence of Treatment-Emergent Adverse Events by Maximum Severity | Safety / Incidence | OBJ2 / END3 | planned |
| T-14-5.06 | Table | Incidence of Treatment-Emergent Adverse Events by Relationship to Study Drug | Safety / Incidence | OBJ2 / END3 | planned |

## 14-6 — Laboratory Data

| ID | Type | Title | Population / Method | Traces-to | Status |
|---|---|---|---|---|---|
| T-14-6.01 | Table | Summary Statistics for Continuous Laboratory Values and Change from Baseline | Safety / Descriptive | OBJ2 / END5 | planned |
| T-14-6.02 | Table | Frequency of Normal and Abnormal (Beyond Normal Range) Laboratory Values During Treatment | Safety / ShiftTable | OBJ2 / END5 | planned |
| T-14-6.03 | Table | Frequency of Normal and Abnormal (Clinically Significant Change from Previous Visit) Laboratory Values During Treatment | Safety / ShiftTable | OBJ2 / END5 | planned |
| T-14-6.04 | Table | Shifts of Laboratory Values During Treatment, Categorized Based on Threshold Ranges, by Visit | Safety / ShiftTable | OBJ2 / END5 | planned |
| T-14-6.05 | Table | Shifts of Laboratory Values During Treatment, Categorized Based on Threshold Ranges | Safety / ShiftTable | OBJ2 / END5 | planned |
| T-14-6.06 | Table | Shifts of Hy's Law Values During Treatment | Safety / ShiftTable | OBJ2 / END5 | planned |

## 14-7 — Vital Signs, Weight, Concomitant Medications

| ID | Type | Title | Population / Method | Traces-to | Status |
|---|---|---|---|---|---|
| T-14-7.01 | Table | Summary of Vital Signs at Baseline and End of Treatment | Safety / Descriptive | OBJ2 / END4 | planned |
| T-14-7.02 | Table | Summary of Vital Signs Change from Baseline at End of Treatment | Safety / Descriptive | OBJ2 / END4 | planned |
| T-14-7.03 | Table | Summary of Weight Change from Baseline at End of Treatment | Safety / Descriptive | OBJ2 / END4 | planned |
| T-14-7.04 | Table | Summary of Concomitant Medications | Safety / Incidence | ICH E3 §11.2 | planned |

## Figures (global F-14-{seq})

| ID | Type | Title | Population / Method | Traces-to | Status |
|---|---|---|---|---|---|
| F-14-1 | Figure | Time to First Injection-Site Reaction by Treatment Group (Kaplan-Meier) | Safety / KaplanMeier | OBJ2 / END3 | planned |

## Flagged / not currently producible

### Blocked — required data absent, or analysis-set N too small

| Type | Title | Population / Method | Traces-to | Reason |
|---|---|---|---|---|
| Table | Summary of Important Protocol Deviations | Intent-to-Treat / Incidence | ICH E3 §10.2 | blocked: SDTM DV domain absent from inputs/sdtm/ and protocol deviations cannot be derived from any present domain. |
| Table | Primary Endpoint Analysis: ADAS-Cog (11) - Change from Baseline to Week 24 - LOCF | Efficacy / ANCOVA / LOCF | OBJ1 / END1 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no ADAS-Cog (11) data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | ADAS-Cog (11) - Change from Baseline to Week 24 - Completers, Observed Cases, Windowed | Completers / ANCOVA / OC | OBJ1 / END1 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no ADAS-Cog (11) data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | ADAS-Cog (11) - Change from Baseline to Week 24 - Male subjects - LOCF | Efficacy / ANCOVA / LOCF / Sex=Male | OBJ1 / END1 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no ADAS-Cog (11) data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | ADAS-Cog (11) - Change from Baseline to Week 24 - Female subjects - LOCF | Efficacy / ANCOVA / LOCF / Sex=Female | OBJ1 / END1 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no ADAS-Cog (11) data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | ADAS-Cog (11) - Mean and Mean Change from Baseline Over Time | Efficacy / Descriptive | OBJ1 / END1 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no ADAS-Cog (11) data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | Repeated Measures Analysis of ADAS-Cog (11) Change from Baseline to Week 24 | Efficacy / MMRM | OBJ1 / END1 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no ADAS-Cog (11) data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | Primary Endpoint Analysis: CIBIC+ - Summary at Week 24 - LOCF | Efficacy / ANOVA / LOCF | OBJ1 / END2 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no CIBIC+ data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | CIBIC+ - Categorical Analysis - LOCF | Efficacy / CMH / LOCF | OBJ1 / END2 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no CIBIC+ data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | ADAS-Cog (11) - Change from Baseline to Week 8 - LOCF | Efficacy / ANCOVA / LOCF | OBJ3 / END6 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no ADAS-Cog (11) data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | ADAS-Cog (11) - Change from Baseline to Week 16 - LOCF | Efficacy / ANCOVA / LOCF | OBJ3 / END6 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no ADAS-Cog (11) data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | CIBIC+ - Summary at Week 8 - LOCF | Efficacy / Descriptive / LOCF | OBJ3 / END7 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no CIBIC+ data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | CIBIC+ - Summary at Week 16 - LOCF | Efficacy / Descriptive / LOCF | OBJ3 / END7 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no CIBIC+ data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | Mean NPI-X Total Score, Week 4 to Week 24 (Windowed) | Efficacy / Descriptive | OBJ3 / END8 | blocked: instrument absent from delivered SDTM. inputs/sdtm/ is the CDISC SDTM-MSG 'Zanomaline' sample (PHQ-9 / SWLS / HAMD 17 / AVLT-REY); it carries no NPI-X data. See study-model.json normalizer_notes (study-vs-data conflict). |
| Table | Change from Baseline to Week 24 in PHQ-9 Total Score - Completers, Observed Cases, Windowed | Completers / ANCOVA / OC | OBJTS1 / ENDTS1 | blocked: analysis-set N too small to compute. Delivered study has 17 randomized subjects (Placebo 5 / Zanomaline Low 5 / Zanomaline High 7); only 2 subjects have an observed (non-imputed) Week 24 PHQ-9 total, so the observed-cases/completers sensitivity analysis has no estimable treatment contrast. |
| Table | Change from Baseline to Week 24 in PHQ-9 Total Score - Male subjects - LOCF | Efficacy / ANCOVA / LOCF / Sex=Male | OBJTS1 / ENDTS1 | blocked: analysis-set N too small to compute. Delivered study has 17 randomized subjects (Placebo 5 / Zanomaline Low 5 / Zanomaline High 7); the male subgroup is 6 subjects overall (Placebo 2 / Low 1 / High 3); no estimable dose-response contrast. |
| Table | Change from Baseline to Week 24 in PHQ-9 Total Score - Female subjects - LOCF | Efficacy / ANCOVA / LOCF / Sex=Female | OBJTS1 / ENDTS1 | blocked: analysis-set N too small to compute. Delivered study has 17 randomized subjects (Placebo 5 / Zanomaline Low 5 / Zanomaline High 7); the female subgroup is 12 subjects overall (Placebo 3 / Low 4 / High 4); with LOCF-derived endpoints this yields cells too small for an interpretable contrast. |

### Needs clarification — plan under-specified

| Type | Title | Traces-to | Reason |
|---|---|---|---|
| Table | Activities of Daily Living (DAD) | OBJ4 / END9 | needs-clarification: traces to unresolved endpoint Endpoint_9 ('*** To be determined from protocol ***'); requires protocol/SAP clarification before an output can be planned. Independently, no DAD data exists in the delivered SDTM. |
| Table | Extended Cognition - ADAS-Cog (14) | OBJ5 / END10 | needs-clarification: traces to unresolved endpoint Endpoint_10 ('*** To be determined from protocol ***'); requires protocol/SAP clarification before an output can be planned. Independently, no ADAS-Cog (14) data exists in the delivered SDTM. |
| Table | Treatment Response by Apo E Genotype | OBJ6 / END11 | needs-clarification: traces to unresolved endpoint Endpoint_11 ('*** To be determined from protocol ***'); requires protocol/SAP clarification before an output can be planned. Independently, no Apo E genotype data exists in the delivered SDTM. |

## Count reconciliation

| Section | Planned tables | Figures | Listings |
|---|---|---|---|
| 14-1 Disposition / Populations | 4 | — | — |
| 14-2 Demographics | 2 | — | — |
| 14-3 Efficacy (data-aligned) | 5 | — | — |
| 14-4 Exposure | 1 | — | — |
| 14-5 Adverse Events | 6 | 1 | 1 |
| 14-6 Laboratory | 6 | — | — |
| 14-7 Vitals / Conmeds | 4 | — | — |
| **Total producible** | **28** | **1** | **1** |


## Planning assumptions (Mode B — no SAP supplied)

Every variant below rests on convention, not a pre-specified plan. Each carries the note
`"variant assumed — no SAP provided"` in `tlf-plan.json`.

1. **Imputation** — LOCF as the primary single-imputation, from estimand EST1's *Treatment Policy* intercurrent-event strategy; observed-cases/completers as the sensitivity variant (N-gate blocked here).
2. **Sex subgroups** — considered (`needs_subgroup_by_sex=true` by Phase II/III convention) and then **N-gate blocked**: 12 F / 6 M overall, minimum cell 1 subject.
3. **Region subgroups** — not emitted; `DM.COUNTRY` is USA-only.
4. **Kaplan-Meier safety figure** — emitted (`needs_tte_safety_figure=true`); title adapted from the USDM's transdermal application-site wording to the delivered study's **injection-site** reaction (SDTM `FA` category `INJECTION SITE REACTION`, 78 records).
5. **AE family breadth** — the fuller family (discontinuation / deaths / severity / relationship) is emitted beyond the TEAE+SAE core because `AEACN`, `AEOUT`, `AESEV` and `AEREL` are all populated. A reviewer may prune.
6. **Analysis populations** — ITT / Safety / Efficacy / Completers are conventional; the USDM declares only one opaque population (`AP_1`).
7. **Site pooling** — 6 sites (701/704/708/710/711/718) over 17 subjects; `SITEGR1` pooling on randomized counts is mandatory downstream.
8. **Derivation dependencies carried into the ADaM spec** — SWLS has no total-score record (derive from 5 items); AVLT-REY has no `BASELINE` visit (use `SCREENING 2`); HAMD 17 has no scheduled post-baseline visit (baseline summary only); lab "clinically significant change" has no SDTM flag (SAP rule required).

## Next step

Run **`tlf-plan-critic`** for the independent two-way coverage audit before human review.

