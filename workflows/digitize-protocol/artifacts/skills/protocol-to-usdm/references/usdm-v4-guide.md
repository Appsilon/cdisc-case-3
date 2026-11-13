# USDM 4.0 — codes and modelling rules for protocol digitization

The schema is the DDF-RA USDM 4.0.0 API (`inputs/schema/USDM_API.json`, classes under
`components.schemas.<Class>-Input`). Look a class up there when the skeleton does not show a
field you need. Every object carries `id` and `instanceType` (= its class name).

## Codes

Every coded attribute is a `Code` object:

```json
{"id": "Code_7", "code": "C82639", "codeSystem": "http://www.cdisc.org", "codeSystemVersion": "2024-09-27",
 "decode": "Parallel Study", "instanceType": "Code"}
```

`studyPhase` and `blindingSchema` are `AliasCode`s: `{"id": "AliasCode_1", "standardCode": <Code>,
"standardCodeAliases": [], "instanceType": "AliasCode"}`. A Code is an object of its own, so it
needs its own unique id every time it appears — never reuse a Code id for two attributes.

Codes marked ✓ appear in the CDISC pilot USDM; the others are standard NCIt codes for the
same codelists. CORE checks each against its DDF codelist, so a wrong one is caught.

| Attribute | code | decode |
|---|---|---|
| `Organization.type` | C70793 ✓ | Clinical Study Sponsor |
| | C93453 ✓ | Study Registry |
| `StudyTitle.type` | C99905x2 ✓ | Official Study Title |
| | C99905x1 ✓ | Brief Study Title |
| | C94108 ✓ | Study Acronym |
| `studyType` | C98388 ✓ | Interventional Study |
| `studyPhase.standardCode` | C15600 | Phase I Trial |
| | C15601 ✓ | Phase II Trial |
| | C15602 | Phase III Trial |
| | C15603 | Phase IV Trial |
| `model` | C82639 ✓ | Parallel Study |
| | C82637 | Crossover Study |
| | C82640 | Single Group Study |
| | C82638 | Factorial Study |
| `blindingSchema.standardCode` | C15228 ✓ | Double Blind Study |
| | C49659 | Open Label Study |
| | C28233 | Single Blind Study |
| `Objective.level` | C85826 ✓ | Primary Objective |
| | C85827 ✓ | Secondary Objective |
| | C85828 | Exploratory Objective |
| `Endpoint.level` | C94496 ✓ | Primary Endpoint |
| | C139173 ✓ | Secondary Endpoint |
| | C170559 | Exploratory Endpoint |
| `StudyArm.type` | C174268 ✓ | Placebo Control Arm |
| | C174267 ✓ | Active Comparator Arm |
| | C174266 | Experimental Arm |
| `StudyArm.dataOriginType` | C188866 ✓ | Data Generated Within Study |
| `StudyEpoch.type` | C202487 ✓ | Screening Epoch |
| | C101526 ✓ | Treatment Epoch |
| | C202578 ✓ | Follow-Up Epoch |
| `EligibilityCriterion.category` | C25532 ✓ | Inclusion Criteria |
| | C25370 ✓ | Exclusion Criteria |
| `StudyDesignPopulation.plannedSex` | C49636 ✓ | Both |
| | C20197 | Male |
| | C16576 | Female |
| `Encounter.type` | C25716 ✓ | Visit |
| `Encounter.environmentalSettings` | C51282 ✓ | Clinic |
| `Encounter.contactModes` | C175574 ✓ | In Person |
| | C171537 ✓ | Telephone Call |
| `StudyIntervention.role` | C41161 ✓ | Experimental Intervention |
| `StudyIntervention.type` | C1909 ✓ | Pharmacologic Substance |
| `Timing.type` | C201358 ✓ | Fixed Reference |
| | C201356 ✓ | After |
| | C201357 ✓ | Before |
| `Timing.relativeToFrom` | C201355 ✓ | Start to Start |
| | C201353 ✓ | End to Start |

## Study identity

- `study.name`: the sponsor's protocol identifier (e.g. `H2Q-MC-LZZT`). One `StudyVersion`
  (`versionIdentifier` = the protocol version or amendment letter) and one
  `InterventionalStudyDesign`.
- `organizations[0]` = the sponsor; `studyIdentifiers[0]` = the protocol id, `scopeId` → the
  sponsor. `roles` holds exactly one sponsor `StudyRole` (code C70793, `appliesToIds` → the
  StudyVersion, `organizationIds` → the sponsor), as in the skeleton. A registry id (NCT…) only when printed in the protocol, scoped to a `Study Registry`
  organization.
- `titles`: the official title from the title page; a brief title or acronym only if printed.

## Objectives, endpoints, estimands

- Objectives from the objectives section, one per bullet, protocol wording, level as labelled.
- Endpoints: the variables that measure each objective — often stated in the efficacy /
  safety measures or the analysis section ("the primary efficacy variables are…"). Put each
  endpoint under the objective it measures; one objective may have several. `purpose`:
  `Efficacy`, `Safety`, `Pharmacokinetic`, … `text` names the measure and the timepoint
  ("Change from baseline in ADAS-Cog (11) total score at Week 24").
- Every objective needs at least one endpoint. A safety objective's endpoints are the safety
  measures the protocol lists (adverse events, laboratory tests, vital signs, ECG …).
- Estimands: one per primary efficacy endpoint when the analysis section defines the
  population, the variable and the handling of intercurrent events (dropouts, rescue
  medication). Older protocols rarely say "estimand": assemble it from the analysis section
  (e.g. LOCF for early discontinuation ≈ a hypothetical / treatment-policy strategy — name what
  the protocol does in `strategy`), cite the analysis passage, and list it under `inferred`.
  Its `analysisPopulationId` → an `AnalysisPopulation` (ITT, safety, evaluable … as defined in
  the analysis section, protocol wording in `text`); `interventionIds` → the study interventions.

## Arms, epochs, elements, cells

- Arms: one per randomized treatment group, `description` = the dose and regimen as stated.
  Placebo arm → `Placebo Control Arm`; active doses of the study drug → `Experimental Arm`
  (`Active Comparator Arm` only for an approved comparator drug).
- Epochs: the periods every subject passes through, from the design summary / figure, in
  order (Screening, Treatment, Follow-up, …), linked with `previousId` / `nextId`. Split the
  treatment period only where the protocol does (e.g. a titration step at a stated week).
- Elements: the distinct things a subject does in one arm during one epoch ("Screening",
  "Placebo", "Xanomeline 54 mg", "Follow-up"). Shared elements are reused across arms.
- Cells: exactly one `StudyCell` per arm × epoch, `elementIds` → the element(s) of that arm in
  that epoch. Cite arms, epochs and elements to the design summary or figure caption.

## Population and eligibility

- `population`: `description` = the target population; `plannedEnrollmentNumber` (a
  `Quantity`) when a sample size is stated; `plannedSex`, `plannedAge` (a `Range`) only when
  stated; `includesHealthySubjects` from the population; `criterionIds` = every criterion.
- Criteria: one `EligibilityCriterionItem` (in the StudyVersion: `text` = the criterion,
  protocol wording, sub-points included) and one `EligibilityCriterion` (in the design:
  `category`, `identifier` = the protocol's number, `criterionItemId`) per numbered criterion,
  chained with `previousId` / `nextId` in protocol order. Cite each criterion to its own page —
  long exclusion lists span many pages.

## Encounters and the schedule of activities

The schedule may be a table ("Schedule of Events") or — when the table is an attachment that
is not in the document — prose like "Vital signs … will be obtained at all clinic visits" and
"safety labs … at Visits 4, 5, 7, 8, 9, 10, 11, 12, and 13". Build it from what is there:

1. **Encounters**: one per scheduled visit, in order (`previousId` / `nextId`). `name` `V1`,
   `V2`, …; `label` "Visit 3 (Week 0)" / "Screening (Visit 1)"; `description` the study day or
   week. Scheduled telephone contacts are encounters too (`contactModes` Telephone Call).
   Unscheduled and early-termination visits are not on the main timeline.
2. **Activities**: one per distinct assessment or procedure (informed consent, medical history,
   physical examination, vital signs, ECG, chemistry, hematology, urinalysis, each efficacy
   instrument, PK sampling, drug dispensing, concomitant medications, adverse events …).
   Short `name`, fuller `label`. Cite the sentence that defines when it happens.
   Granularity: one activity per separately named instrument, test panel or procedure —
   chemistry, hematology and urinalysis are three activities, not "safety labs"; screening
   scales the eligibility criteria rely on (e.g. MMSE, Hachinski) are activities at the visit
   that administers them; placing and removing a device (an ambulatory ECG) are two.
3. **Main timeline**: one `ScheduledActivityInstance` per encounter, in visit order:
   `encounterId`, `epochId` (the epoch the visit falls in), `activityIds` = every activity done
   at that visit — expand "at all clinic visits" to each clinic visit, and "at Visits 4, 5,
   7 …" to exactly those. `defaultConditionId` → the next instance; the last instance has
   `timelineExitId` → the timeline's exit. `entryId` → the first instance.
4. **Timings** (in the timeline's `timings`): one anchor `Fixed Reference` timing on the
   anchor visit (usually randomization / Day 1 / Week 0), then one per other instance:
   `type` `After` (or `Before` for screening), `value` an ISO-8601 duration from the anchor
   (`P14D`, `P2W`), `valueLabel` ("Week 2"), `relativeFromScheduledInstanceId` = this
   instance, `relativeToScheduledInstanceId` = the anchor instance, `relativeToFrom`
   `Start to Start`; visit windows ("within 3 days") in `windowLower` / `windowUpper`
   (`P3D`) and `windowLabel`. Point each encounter's `scheduledAtId` to its timing.
5. **Citations**: each encounter → where the visit and its week are defined; each instance →
   the most specific sentence placing activities at that visit (the same sentence may support
   several instances); each activity → where it is described.

Every activity must be scheduled at least once, and every encounter must have an instance on
the main timeline — the gate checks both.

## Ids and references

- `<Class>_<n>` ids, unique across the whole document.
- `name` unique within a class (CORE checks it): two arms, encounters or activities never share a
  name — qualify them ("Vital signs (screening)", "V2") rather than repeating one.
- References are ids: `scopeId`, `armId`, `epochId`, `elementIds`, `criterionItemId`,
  `criterionIds`, `analysisPopulationId`, `interventionIds`, `variableOfInterestId`,
  `encounterId`, `activityIds`, `entryId`, `defaultConditionId`, `timelineExitId`,
  `scheduledAtId`, `previousId`, `nextId`, `relative…ScheduledInstanceId`. Every one must name
  an object that exists in the document — the gate checks all of them.
