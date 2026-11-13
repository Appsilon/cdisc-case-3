# TLF Plan Coverage Report — CDISCPILOT01

**Audited:** `outputs/tlf-plan/tlf-plan.json` against `outputs/tlf-plan/study-model.json`
**Date:** 2026-07-29 · **Auditor:** `tlf-plan-critic` (read-only; the plan was not modified)
**Inputs read:** the plan and the study model only — not the planner's reasoning.

---

## ✅ Post-audit resolution (appended after human review, 2026-07-29)

Two findings from this report were resolved before `tlf-analysis-spec` ran. The audit body below is
preserved unedited as the record of what was found; this block records what changed.

| Finding | Resolution | Re-audit result |
|---|---|---|
| **B-1** — §14-3 traced to a fabricated `regulatory_rule` | `study-model.json` gained 3 source-tagged objectives (`Objective_TS1/TS2/TS3`) and 4 endpoints (`Endpoint_TS1..TS4`) transcribed from SDTM `TS.OBJPRIM`/`TS.OUTMSPRI`. Every USDM entry now carries `source:"USDM"`, every TS entry `source:"SDTM TS"`, so the pure-USDM view is recoverable by filter. The 9 data-aligned candidates were re-pointed at them and the placeholder `regulatory_rule` cleared. | **closed** — 0 pseudo-scaffolding candidates remain; every efficacy TLF has a real Objective→Endpoint link. |
| **R-3** — HAMD 17 filed as an efficacy analysis | Recategorized `efficacy`→`demographics` (§14-3 → §14-2), retitled "Summary of HAMD 17 Total Score at Baseline", population Efficacy→Intent-to-Treat. `Endpoint_TS2` remains covered by it. | **closed** — §14-3 now contains only treatment-effect analyses. |

**Re-audit (post-fix):** 7 of 12 resolved endpoints covered · 4 of 9 objectives covered · **0 orphans,
0 dangling ids, 0 pseudo-scaffolding** · 5 soft gaps unchanged (END1/2/6/7/8, still data-blocked) ·
3 clarification items unchanged (END9/10/11).

Numbering shifted: §14-2 gained T-14-2.02, and §14-3 contracted from 6 tables to 5
(T-14-3.01 PHQ-9 ANCOVA · .02 SWLS · .03 AVLT-REY · .04 PHQ-9 MMRM · .05 PHQ-9 descriptive).

Findings **R-1, R-2, R-4 … R-8 remain open** and are carried forward as caveats, not blockers.
The verdict below is **unchanged** — the 5 soft gaps and 3 clarification items are inherited from
the inputs and cannot be closed by re-planning.

---

## Verdict

# `gaps-found`

**5 of 8 resolved endpoints (END1, END2, END6, END7, END8) and 2 of 6 objectives — including the
study's PRIMARY efficacy objective OBJ1 — have zero producible output.** All 5 are *soft gaps* under
Rule F3: they are covered only by `blocked` candidates, and the block is a **data-feasibility
failure, not a planning miss**. Per §4 of the audit checklist this must **not** trigger a
`tlf-planner` re-run loop — it escalates to a human as an input-integrity issue.

A second, independent finding raises the severity: **the plan's entire §14-3 efficacy section
(T-14-3.01–.06) traces to no objective and no endpoint in the study model.** It passes the letter of
Rule B2 only because a non-null `regulatory_rule` was populated with a value that is not a
regulatory rule. See Backward audit finding **B-1** — this is the most consequential item in this
report.

---

## Counts

| Metric | Value |
|---|---|
| Objectives | 6 (2 primary, 4 secondary) |
| Endpoints | 11 (8 resolved, 3 unresolved) |
| Total candidates | 50 |
| — `planned` | 30 (28 tables, 1 figure, 1 listing) |
| — `blocked` | 17 |
| — `needs-clarification` | 3 |
| Planned TLFs traceable to an objective/endpoint | **16 of 30** |
| Planned TLFs justified only by `regulatory_rule` | **14 of 30** (8 genuine ICH E3 + **6 pseudo**) |
| True orphans (Rule B1) | 0 |
| Referential-integrity errors (Rule B3) | 0 |
| Coverage gaps (planning) | 0 |
| Coverage gaps (blocked / feasibility) | **5 endpoints, 2 objectives** |
| Clarification action items | 3 (END9, END10, END11) |

---

## 1. FORWARD audit — coverage

### Endpoint coverage (Rule F1)

| Endpoint | Measure | Level | Resolved | Planned TLFs | Status |
|---|---|---|---|---|---|
| END1 | ADAS-Cog (11) Wk 24 | Primary | yes | — (6 blocked) | **gap (blocked)** |
| END2 | CIBIC+ Wk 24 | Primary | yes | — (2 blocked) | **gap (blocked)** |
| END3 | Adverse events | Primary | yes | T-14-5.01–.06, F-14-1 | covered |
| END4 | Vital signs | Primary | yes | T-14-7.01, .02, .03 | covered |
| END5 | Laboratory evaluations | Primary | yes | T-14-6.01–.06 | covered |
| END6 | ADAS-Cog (11) Wk 8 & 16 | Secondary | yes | — (2 blocked) | **gap (blocked)** |
| END7 | CIBIC+ Wk 8 & 16 | Secondary | yes | — (2 blocked) | **gap (blocked)** |
| END8 | NPI-X Wk 4–24 | Secondary | yes | — (1 blocked) | **gap (blocked)** |
| END9 | *** To be determined *** | Secondary | **no** | — | clarification |
| END10 | *** To be determined *** | Secondary | **no** | — | clarification |
| END11 | *** To be determined *** | Secondary | **no** | — | clarification |

3 of 8 resolved endpoints covered. All 3 covered endpoints belong to the safety objective OBJ2.

### Objective coverage (Rule F2)

| Objective | Level | Endpoints | Status |
|---|---|---|---|
| OBJ1 — relationship between ADAS-Cog (11)/CIBIC+ change and dose | **Primary** | END1, END2 | **GAP (blocked)** |
| OBJ2 — document the safety profile | Primary | END3, END4, END5 | covered (16 TLFs) |
| OBJ3 — dose-dependent improvement in behavior (NPI-X) | Secondary | END6, END7, END8 | **GAP (blocked)** |
| OBJ4 — activities of daily living (DAD) | Secondary | END9 | clarification |
| OBJ5 — extended cognition (ADAS-Cog (14)) | Secondary | END10 | clarification |
| OBJ6 — response by Apo E genotype | Secondary | END11 | clarification |

**Only one of six objectives — the safety objective — is actually served by this plan.** The study's
confirmatory efficacy claim (OBJ1) has no producible output.

### Root cause (single, shared)

Every blocked efficacy candidate carries the same `status_reason`: the instrument is absent from
`inputs/sdtm/`. The study model's `normalizer_notes` records the reason — the USDM defines a
xanomeline TTS study measured by ADAS-Cog / CIBIC+ / NPI-X / DAD, while the delivered SDTM is the
Zanomaline sample study measured by PHQ-9 / SWLS / HAMD 17 / AVLT-REY. The two do not describe the
same trial. This is an **input-integrity defect upstream of the planner**; no amount of re-planning
resolves it.

---

## 2. BACKWARD audit — provenance

**True orphans (Rule B1): 0.** Every candidate carries at least one of `objective_ids`,
`endpoint_ids`, or a non-null `regulatory_rule`.

**Referential-integrity errors (Rule B3): 0.** No dangling ids. Three candidates cite unresolved
endpoints (`clar-END9/10/11-placeholder`) — these are explicitly-labelled clarification
placeholders at `status: needs-clarification`, not analyses, and are the intended representation
of a TBD endpoint rather than a B3 violation.

### Genuine scaffolding — valid under Rule B2 (8 candidates)

| TLF | Title | regulatory_rule |
|---|---|---|
| T-14-1.01 | Summary of Populations | ICH E3 §11.1 |
| T-14-1.02 | Summary of End of Study Data | ICH E3 §10.1 |
| T-14-1.03 | Summary of Number of Subjects by Site | ICH E3 §10.1 |
| T-14-1.04 | Summary of Medical History | ICH E3 §11.2 |
| T-14-2.01 | Summary of Demographic and Baseline Characteristics | ICH E3 §11.2 |
| T-14-4.01 | Summary of Planned Exposure to Study Drug | ICH E3 §12.1 |
| T-14-7.04 | Summary of Concomitant Medications | ICH E3 §11.2 |
| L-14-5.01 | Listing of Deaths | ICH E3 §12.3 |
| *(blocked)* | Summary of Important Protocol Deviations | ICH E3 §10.2 |

### 🔴 B-1 — Pseudo-scaffolding: the entire §14-3 section is untraceable

Ten candidates (6 `planned`, 4 `blocked`) carry:

```
"traces_to": { "objective_ids": [], "endpoint_ids": [],
               "regulatory_rule": "Delivered-data objective (SDTM TS OBJPRIM / OUTMSPRI)" }
```

Affected planned TLFs: **T-14-3.01, .02, .03, .04, .05, .06** — i.e. **100% of the plan's efficacy
section**.

This clears Rule B2's mechanical test (`regulatory_rule != null`) but defeats its purpose. ICH E3
section references justify an output that *no objective points to*; `SDTM TS OBJPRIM/OUTMSPRI` is
not a regulatory rule — it is a pointer into the delivered dataset. The consequence is concrete:

* These tables **cannot be traced to any objective or endpoint** in `study-model.json`. The
  Objective → Endpoint → ADaM → TLF chain that the downstream traceability explorer is meant to
  render is **broken at the first link** for every efficacy output.
* The `regulatory_rule` field is being used as an escape hatch. A future automated audit reading only
  the schema will report "0 orphans" and miss this entirely.

**This is a deliberate, documented substitution** — the plan records the human review decision of
2026-07-29 on each affected candidate, and the critic accepts the decision as made. The finding is
that the *mechanism* is wrong, not the decision.

**Recommendation (blocking for traceability, not for compute):** before the traceability build,
either
(a) add the SDTM `TS`-declared objectives to `study-model.json` as first-class objectives/endpoints
with an explicit `source: "SDTM TS"` marker, and re-point `traces_to.objective_ids` /
`endpoint_ids` at them; **or**
(b) accept the break and require the traceability explorer to render §14-3 under an explicit
"unlinked — data-derived" cluster so the gap is visible rather than papered over.
Option (a) is preferable and cheap. Either way, stop overloading `regulatory_rule`.

---

## 3. COMPLETENESS audit — conventions

| # | Check | Result |
|---|---|---|
| C1 | Safety objective → deaths/mortality table | ✅ T-14-5.04 + L-14-5.01 (3 deaths in DD) |
| C2 | Safety objective → AEs leading to discontinuation | ✅ T-14-5.03 |
| C3 | Primary continuous endpoint → OC/completers sensitivity | ⚠️ emitted (`da-phq9-ancova-wk24-oc`) then **N-gate blocked** — only 2 observed Week-24 records |
| C4 | Primary continuous endpoint → MMRM companion | ✅ T-14-3.04 |
| C5 | Primary endpoint → subgroup split | ⚠️ emitted (male/female) then **N-gate blocked** — 12 F / 6 M, minimum cell 1 |
| C6 | Multi-site → by-site table | ✅ T-14-1.03 (6 sites) |
| C7 | Lab endpoint → shift / Hy's-Law tables | ✅ T-14-6.02–.06 |
| C8 | Disposition + demographics scaffolding | ✅ T-14-1.01/.02, T-14-2.01 |
| C9 | TTE safety signal flagged → KM figure | ✅ F-14-1 |
| C10 | Safety objective → exposure table | ✅ T-14-4.01 |

C3 and C5 are satisfied *as plan intent* and unsatisfiable *as output*. That is the correct
representation — the candidates exist and carry an explicit N-gate reason — but a reader of the
final CSR shell list must not mistake their presence in `tlf-plan.json` for deliverability.

### Critic-originated findings (not on the standard checklist)

| # | Finding | Severity | Recommendation |
|---|---|---|---|
| **R-1** | **N = 17 randomized** (Placebo 5 / Low 5 / High 7). Every LS-mean, contrast, CMH and log-rank in this plan is uninterpretable, and the downstream ADaM N-gate will trip. | **High** | Proceed only as a pipeline-mechanics demonstration. Every generated table must carry a standing footnote declaring the results non-interpretable. |
| **R-2** | **T-14-3.01/.02 rest almost entirely on imputation.** Only 2 subjects have an observed Week-24 PHQ-9 or SWLS record against 13 at baseline. The LOCF rule will manufacture ~11 of ~13 analysis values. | **High** | Report `n(observed)` alongside `n(analyzed)` on the table face, not only in a footnote. Consider promoting the MMRM (T-14-3.04) to the headline analysis — it uses all observed visits and is the least damaged by this sparsity. |
| **R-3** | **T-14-3.05 (HAMD 17, baseline only)** carries no treatment-effect content. RS has no scheduled post-baseline visit. A baseline-only summary is a §14-2 baseline characteristic, not a §14-3 efficacy analysis. | Medium | Recategorize to `demographics` (§14-2) or drop. Filing it under Efficacy overstates the section's content. |
| **R-4** | **No categorical, ordinal or responder analysis anywhere in the plan.** The USDM's global-impression endpoints (END2/END7 → CMH) are blocked, and the promoted data-aligned block is entirely continuous ANCOVA. | Medium | If PHQ-9 severity bands (0–4 / 5–9 / 10–14 / 15–19 / 20–27) are of interest, add a shift or responder table. Otherwise record the absence as intentional. |
| **R-5** | **T-14-1.04 (Medical History)** degenerates to one row: MH is uncoded and holds the single term "ALZHEIMER'S DISEASE" for all 17 subjects. | Low | Prune, or fold into T-14-2.01 as a baseline-condition line. |
| **R-6** | **T-14-7.04 (Concomitant Medications)** cannot present a therapeutic class — CM has no `CMDECOD`/`CMCLAS` in this extract. | Low | Summarize by verbatim `CMTRT` and footnote the absence of WHO-DD coding. |
| **R-7** | **F-14-1 title deviates from the USDM endpoint wording** — "injection-site" (delivered subcutaneous study) vs the USDM's transdermal application-site signal. The deviation is documented on the candidate. | Low | Correct given the data; record it as a reporting deviation in the CSR rather than silently retitling. |
| **R-8** | **Protocol deviations (ICH E3 §10.2) have no output** — SDTM `DV` is absent and deviations are not derivable. | Medium | Confirm with the sponsor that no DV dataset exists. If the CSR requires §10.2 content, this is a data-transfer gap, not a planning gap. |

---

## 4. Clarification action items

1. **END9 (OBJ4 — Disability Assessment for Dementia / activities of daily living):** endpoint text is
   `"*** To be determined from protocol ***"`. Independently, no DAD data exists in the delivered
   SDTM. Resolve the endpoint definition with the protocol/SAP **and** confirm whether DAD was
   collected at all.
2. **END10 (OBJ5 — extended cognition, ADAS-Cog (14)):** unresolved endpoint text; no ADAS-Cog data
   in the delivered SDTM. Same double resolution required.
3. **END11 (OBJ6 — treatment response by Apo E genotype):** unresolved endpoint text; no genotype
   variable in any delivered domain (`PF`/`SUPPDM` carry no ApoE). Same.

All three are **double gaps** — the plan is under-specified *and* the data is absent. Resolving the
endpoint text alone will not make them producible.

---

## 5. Routing / re-run plan

Per §4 of the audit checklist, gaps route to a `tlf-planner` phase. **None of this report's gaps do.**

| Finding | Normal route | Actual route |
|---|---|---|
| END1/2/6/7/8 uncovered | phase 3b (efficacy) | ❌ **do not re-run.** Coverage-by-blocked-TLF → feasibility escalation (checklist §4, last row). The planner emitted every correct candidate; the data cannot support them. |
| B-1 pseudo-scaffolding | — | Escalate to the pipeline owner before `traceability-builder`. Fix in `study-model.json`, not by re-running a planner phase. |
| C3 / C5 unsatisfiable | phase 4 (variants) | ❌ **do not re-run.** The variants exist; they are N-gate blocked. Re-running phase 4 would regenerate identical blocked candidates. |
| R-3 / R-5 recategorization | phase 6 (consolidation) | Optional, cosmetic. Defer to human review. |
| END9/10/11 | — | Human/protocol action items. |

**No planner re-run is warranted. 0 of 2 permitted rounds consumed.**

### Escalation to the human reviewer

1. **Confirm the input substitution** (already decided 2026-07-29) — or supply the SDTM that matches
   the supplied USDM, which would unblock 13 efficacy tables and close both objective gaps.
2. **Fix the B-1 traceability mechanism** before the traceability build.
3. **Accept the N=17 caveat** in writing, so the downstream N-gate failure is a recorded decision
   rather than a surprise.

---

## 6. Sign-off

**`gaps-found` — proceed downstream with escalation, not with a re-run.**

The plan is internally sound: zero orphans, zero integrity errors, correct unresolved-endpoint
handling, and all ten conventional completeness checks addressed. Its defects are inherited from its
inputs, not manufactured by the planner. The three items in §5 must be acknowledged by a human before
`tlf-analysis-spec` runs; none of them blocks compute.
