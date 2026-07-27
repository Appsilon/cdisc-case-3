# tlf-analysis-spec — lessons learned

Append-only. New lessons are added by the skill-refinement loop (propose-skill-lesson → open-skill-pr) from reviewer feedback.

### 2026-07-27 — run CDISCPILOT01

**Context:** build-specs emitting the ARS ReportingEvent (reporting-event.json) alongside analysis-spec.json and adam-spec.json.

- **Lesson:** Write `reporting-event.json` directly to the workspace/output root (e.g. `/workspace/reporting-event.json`), never into the nested `outputs/{study}/tlf-plan/` directory used for `analysis-spec.json` and `adam-spec.json` — it is the one artifact of the three that the output contract lists without that prefix, and `validate-ars` only looks for it at the root. **Why:** validate-ars failed on the first pass with "reporting-event.json not found in /workspace or /output" because the reporting-event build step wrote it into the same nested plan directory as the other two spec files instead of the root.
