# tlf-analysis-spec — lessons learned

Append-only. New lessons are added by the skill-refinement loop (propose-skill-lesson → open-skill-pr) from reviewer feedback.

### 2026-10-12 — run CDISCPILOT01

**Context:** build-specs emitted reporting-event.json, analysis-spec.json, and adam-spec.json only under the nested `outputs/{study}/tlf-plan/` path. The automated `validate-ars` gate checks for these three files directly at the `/workspace` and `/output` roots and does not recurse into subdirectories, so attempt 1 failed with "reporting-event.json not found" even though the file existed and was content-correct.

- **Lesson:** Always write `reporting-event.json`, `analysis-spec.json`, and `adam-spec.json` to BOTH the nested `outputs/{study}/tlf-plan/` path (needed by downstream `sdtm-to-adam` and `tlf-generator` skills) AND directly at the `/workspace` and `/output` roots (e.g. `/workspace/reporting-event.json`, `/output/reporting-event.json`) in the same step that authors them — do not wait for the `validate-ars` gate to fail first. **Why:** attempt 1 of `validate-ars` failed purely on file placement, not on schema or referential-integrity content, costing a full re-entry cycle to fix a one-line output-path issue.
