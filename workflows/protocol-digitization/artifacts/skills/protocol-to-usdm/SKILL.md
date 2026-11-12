---
name: protocol-to-usdm
description: Read a clinical study protocol (PDF text, page by page) and write its study definition as a USDM 4.0 JSON document plus a citation for every extracted entity (the page and a verbatim quote). Scope v1 - study identity, objectives, endpoints, estimands, arms / epochs / elements / cells, population with inclusion and exclusion criteria, encounters and the schedule of activities.
---

# Protocol → USDM 4.0

You are a clinical data standards specialist digitizing a protocol. Your output is read by
scripts and by a clinical scientist: a deterministic gate validates it against the official
USDM 4.0 schema, checks every reference and every citation, then CDISC CORE runs its USDM
rules, then a human reviews it entity by entity next to your quotes. Accuracy and traceability
matter more than coverage: **never invent** a value the protocol does not state.

## Inputs (read-only)

- `/workspace/protocol-digitization/inputs/protocol/protocol.txt` — the whole protocol,
  `=== Page N ===` before each page. N is the **physical PDF page, 1-based** — the number a
  citation uses, which can differ from the page number printed on the page.
- `.../inputs/protocol/pages/page-NNN.txt` — the same text, one file per page. The citation
  check compares against exactly these files.
- `.../inputs/sap/` — the SAP, same layout, when one was provided (context; you may cite it
  with `"document": "sap"`).
- `references/usdm-skeleton.json` — a schema-valid USDM 4.0 document with one instance of
  every class in scope. **Start from a copy of it.**
- `references/usdm-v4-guide.md` — the controlled-terminology codes to use, the modelling
  rules, and how to read a schedule of activities out of prose.

## Outputs

Write to `/workspace/protocol-digitization/usdm/`:

1. `usdm.json` — the USDM 4.0 Wrapper (`{"usdmVersion": "4.0.0", "study": {...}, ...}`).
2. `usdm-citations.json` — one entry per extracted entity:
   ```json
   {"Objective_1": {"page": 7, "quote": "To determine if there is a statistically significant relationship"},
    "Endpoint_3":  {"page": 41, "quote": "...", "document": "protocol"}}
   ```
   `quote` is copied **verbatim** from that page (at least 20 characters, a phrase that states
   the fact — not a heading). Line breaks and spacing do not matter; spelling does. Copy from
   the page text as extracted, artefacts included: a bullet may read `x`, a Greek letter may
   read as a Latin one (`D=.05` for α=.05) — the `text` fields in usdm.json may use the
   correct characters, the quote may not. Required
   for every `Objective`, `Endpoint`, `Estimand`, `StudyArm`, `StudyEpoch`, `StudyElement`,
   `EligibilityCriterion`, `StudyDesignPopulation`, `Encounter`, `Activity` and
   `ScheduledActivityInstance` (cite the sentence that puts those activities at that visit).

Then `/output/result.json`: `{"summary": "<one paragraph: what you extracted, what the protocol
does not state, what you modelled by inference>", "counts": {...}, "inferred": ["<entity id>: <why>"]}`.

## Procedure

1. Read `protocol.txt` end to end once. Note the pages for: title page, objectives, design
   summary and design figure, population / inclusion / exclusion, treatments, the schedule of
   events (a table, or prose like "vital signs ... at all clinic visits"), efficacy and
   safety measures, analysis populations and statistical methods.
2. Copy `references/usdm-skeleton.json` to `usdm/usdm.json` and replace every `<...>`
   placeholder; add instances by copying the example ones. Keep ids `<Class>_<n>` and unique
   across the whole document (Code ids too: `Code_1`, `Code_2`, ...).
3. Fill each part following `references/usdm-v4-guide.md`, writing the citation as you go.
4. Run `python3 /artifacts/scripts/self_check.py` (no attempt is used). Fix what it reports and
   repeat until it prints `PASS`. Do not finish before PASS.
5. Write `/output/result.json`.

## Feedback

- `/workspace/protocol-digitization/feedback.json` exists → the gate rejected your last
  output: fix exactly the problems it lists, keep everything else.
- `/workspace/protocol-digitization/review-feedback.jsonl` exists → its **last line** is the
  request to act on now. From the clinical scientist (no `source`) or from CDISC CORE
  (`"source": "core"`; the flagged instances, their JSON paths and values are in
  `/workspace/protocol-digitization/core-feedback.json`). Change only what is asked; keep the
  ids of untouched entities stable, and edit the existing `usdm/usdm.json` instead of starting over.

## Rules

- Protocol wording for `text` fields (objectives, endpoints, criteria): copy, don't paraphrase.
  Split a numbered criterion list into one criterion per number; keep the protocol's number in
  `identifier`.
- What the protocol does not state, leave out (optional fields `null` / `[]`). Never fill a
  gap from general knowledge of the drug or the disease. If a required field has no source,
  use the most neutral honest value (e.g. `rationale`: "Not stated in the protocol.") and list
  it under `inferred` in result.json.
- An inference you must make (e.g. an epoch boundary implied by the design figure, an estimand
  assembled from the primary objective + the analysis section) is allowed when the protocol
  supports it; cite the passage it rests on and list it under `inferred`.
- Codes: only the C-codes in the guide's tables. If none fits, pick the closest generic one and
  say so under `inferred` — never make up a code.
