# tlf-analysis-spec — lessons learned

Append-only. New lessons are added by the skill-refinement loop (propose-skill-lesson → open-skill-pr) from reviewer feedback.

### 2026-10-12 — run CDISCPILOT01

**Context:** build-specs (ARS ReportingEvent output) — caught by the validate-ars gate before human review, attempt 1/3.

- **Lesson:** Always write `reporting-event.json` to the bare root paths `/workspace/reporting-event.json` and `/output/reporting-event.json`, in addition to (not instead of) the nested `outputs/{study}/tlf-plan/reporting-event.json` copy. Unlike `analysis-spec.json` and `adam-spec.json`, whose output contract paths explicitly include the `outputs/{study}/tlf-plan/` prefix, the `reporting-event.json` contract path is bare — the validate-ars gate only looks at the root. **Why:** validate-ars failed with "reporting-event.json not found in /workspace or /output" even though a schema-valid, fully-authored reporting-event.json already existed under the nested tlf-plan directory; the content was correct, only the emission path was wrong.
