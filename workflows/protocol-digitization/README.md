# protocol-digitization

Turn a clinical study protocol (PDF) into a USDM 4.0 study definition in which
every extracted entity cites the page and the verbatim quote it came from. Part
of the modular protocol-to-TFL set: runs on its own (upload the protocol) or
inside a parent workflow (study package with a `protocol` in the trigger), and
hands `tlf-planning` the `usdm` it needs.

```
resolve-inputs ─needsUpload─► upload-protocol ─► stage-inputs
       └──────── package ──────────────────────────┘    │
                                                         ▼
 ┌──────────────────────────────────────────────► extract-usdm ─► check-usdm ─needsFix, retry─► extract-usdm
 │                                                                     │ pass
 │                                                                     ▼
 │                               validate-usdm (child: cdisc-core-validation, usdm 4-0)
 │                                 │ rejected                         │ accepted
 ├── record-core ◄── route-core ◄──┘                                   ▼
 │                                                     prepare-review ─► review-usdm ─approve─► return-result ─► done
 └── record-review ◄────────────────────────────────────────────────────── revise ─┘
  check-usdm needsFix, no attempts left · validate-usdm not completed · route-core after the 3rd rejection ─► return-result (outcome failed)
```

| Step | Executor | What it does |
|---|---|---|
| `resolve-inputs` | script | Package mode: exactly one `protocol` (+ optional `sap`). Standalone: routes to the upload. |
| `upload-protocol` | human (`clinical-scientist`) | The protocol PDF; optionally the SAP (`sap` or `statistical` in the file name). Text PDFs only — no OCR. |
| `stage-inputs` | script | sha256-verifies the PDFs and extracts the text layer with pypdf: `inputs/<protocol\|sap>/pages/page-NNN.txt` (physical page, 1-based — the number a citation names) and `<doc>.txt` with `=== Page N ===` markers. Copies the image's USDM 4.0 schema to `inputs/schema/USDM_API.json`. |
| `extract-usdm` | **agent** | `protocol-to-usdm` skill (carried in `artifacts/skills/`): starts from `references/usdm-skeleton.json` (schema-valid, one instance per class in scope), follows `references/usdm-v4-guide.md` (C-codes, modelling rules, the schedule of activities from a table or from prose). Writes `usdm/usdm.json` + `usdm/usdm-citations.json`, runs `self_check.py` until PASS. |
| `check-usdm` | script | The deterministic gate (`usdmlib.check_usdm`, below). Fails go back to the agent in `feedback.json`, three attempts per round. On pass publishes `usdm.json`, `usdm-citations.json` and the package for CORE (carrying the previous round's USDM dispositions). |
| `validate-usdm` | `run-workflow` | `cdisc-core-validation` (pinned), `standard=usdm`, `version=4-0`, `onReject=return`. The standards reviewer's disposition task lives in the child run. |
| `route-core` | script | After a rejection: counts the round and lifts the child's `core-report.json` + `core-dispositions-usdm.json` to top-level `files` (the runtime downloads only those). After the 3rd rejection in one review round (`record-review` restarts the count) → `return-result`. |
| `record-core` | script | This round's `fix` dispositions → `core-feedback.json` (per rule: message, reviewer note, up to 25 flagged instances with id, JSON path and values) and a request line (`"source": "core"`) in `review-feedback.jsonl`; fresh gate attempts. |
| `prepare-review` | script | Renders `usdm-review.html` from the copy `check-usdm` published, with CORE's verdict on top. Its own step because a review shows the output of the step just before it, which would otherwise be the CORE child. |
| `review-usdm` | human review (`clinical-scientist`) | `usdm-review.html`: objectives/endpoints, estimands, arms, the arm × epoch element matrix, population and criteria, the schedule of activities grid — each with a page chip (hover = the quote). Approve, or request changes with a comment. |
| `record-review` | script | Appends the comment to `review-feedback.jsonl` (the agent acts on the last line; skill learning reads all) and resets the gate's attempts. |
| `return-result` | script | `outcome` `digitized` — on top of the CORE child's package: `usdm` and `usdm-citations` exactly as `check-usdm` checked them, `usdm-view` (the review page), the CORE files, `review-feedback-protocol-digitization` — or `failed` (the agent's files and any CORE files attached, the package's USDM unchanged). |

## The AI / deterministic boundary

The agent reads the protocol and writes the USDM and the citations. The gate is
a script and decides what can be decided for certain:

- `usdm.json` validates against the **official USDM 4.0 schema** (on a schema
  failure the checks below wait until the shape is fixed) — the DDF-RA
  `USDM_API.json` at a pinned commit, sha256-checked when the image is built;
  errors inside an `anyOf` are reported for the branch the object means (its
  `instanceType`; never the `null` branch of a nullable object), repeated errors
  collapse per path pattern;
- `usdmVersion` is `4.0.0`; ids are unique and every `*Id` / `*Ids` value names
  an object in the document;
- the v1 scope is present and wired: objectives (≥ 1 primary, each with
  endpoints, non-empty text), arms, epochs, elements, one study cell per arm ×
  epoch, inclusion and exclusion criteria with text, encounters and activities,
  exactly one main timeline with every encounter on it, every activity scheduled;
- every `Objective`, `Endpoint`, `Estimand`, `StudyArm`, `StudyEpoch`,
  `StudyElement`, `EligibilityCriterion`, `StudyDesignPopulation`, `Encounter`,
  `Activity` and `ScheduledActivityInstance` has a citation, and every
  citation's quote (≥ 20 characters) is found on the page it names — compared
  after NFKC, plain quotes and dashes, no whitespace, case-folded, because PDF
  text breaks lines and spaces words unpredictably.

CORE then applies the CDISC USDM 4.0 conformance rules (codelists, cardinalities
the schema cannot express). Whether the extraction is *right* — the right
endpoints, the right visits — stays with the clinical scientist, who sees every
entity next to its source.

## Package kinds

Reads `protocol` (exactly one), `sap` (optional). Writes `usdm`, `usdm-citations`,
`usdm-view`, `core-report-usdm`, `core-issue-index-usdm`, `core-dispositions-usdm`,
`review-feedback-protocol-digitization`; in upload mode also the uploaded `protocol`
/ `sap`. A new `protocol` makes `usdm` and the USDM dispositions and issue index stale; a
new `usdm` makes its citations, view, CORE report and everything planned from it stale
(`../shared/mfpkg.py` `DOWNSTREAM`). USDM dispositions and the issue index survive a
re-extraction — `check-usdm` carries them into the next CORE round — so it shows
"N new, M fixed" and pre-fills earlier decisions.

## Image

Script steps build from the carried `artifacts/Dockerfile` (python:3.12-slim,
pypdf 7.0.1, jsonschema 4.26.0, `USDM_API.json` from DDF-RA
`aa303cb3`); the agent runs in the catalog image `mediforce-built:5d4c205d6727`
(agent-capable, has jsonschema) and its self-check reads the schema copy that
`stage-inputs` put in the workspace, so both validate against the same bytes.
`validate-usdm` pins `cdisc-core-validation` **v3** (staging `vedha` in `workflow.json`; prod
`appsilon` via `pins/prod-appsilon.json`, also v3) — bump the pin when that child is re-registered.

## Not yet

- Scanned PDFs (no OCR), Word protocols.
- Biomedical concepts, procedures, narrative content, amendments, sub-timelines
  (AE / early termination) — out of the v1 scope; CORE flags some of them
  (e.g. CORE-001076 "activity refers to no procedure or BC"): disposition them.
- The ground-truth comparison runs locally only (`tests/compare_usdm.py`).

## Test

```bash
PROTOCOL_PDF=<cdiscpilot01-protocol.pdf> python3 tests/test_pipeline.py   # needs pypdf + jsonschema
python3 tests/compare_usdm.py <extracted usdm.json> ~/Repo/FULL_WORKFLOW/inputs/usdm.json
```

The protocol PDF is not committed (© Eli Lilly; public CDISC pilot material). The
schema is fetched once into `~/.cache/mediforce/` at the Dockerfile's commit and
sha256. The agent stand-in `tests/fixtures/usdm` is a CDISCPILOT01 extraction made
by the skill. Covers package mode, a broken extraction through three gate attempts
to `failed`, a malformed shape (gate problems, not a crash), upload mode with a CORE
fix round and a review round, and CORE rejecting three times. `compare_usdm.py` scores an extraction against the CDISC
pilot USDM (same study): matched / missing / extra per entity type and the
schedule's precision and recall.
