"""Close the planning run: publish the approved plan and hand the study package back.

outcome:
  planned  the gate passed, the critic audited it and the statistician approved;
           publishes the files exactly as the gate checked them (check-plan's
           output): study-model, tlf-plan (json), tlf-plan-view (index md + html),
           plus the critic's coverage-report and the review feedback.
  data-mismatch  the SDTM is not the study the USDM describes (check-study), or it
           cannot answer a primary endpoint (check-plan dataBlocked); publishes the
           data-check page (and the plan drafts) and leaves the package's plan as it was.
  failed   the gate still failed after the last attempt; publishes what the
           planner wrote, for a human to pick up, and leaves the package's plan as it was.

Result: { outcome, counts, verdict, summary, files, package }
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gate import publish_copy  # noqa: E402
from mfpkg import read_input, replace_files, run_main, step_file, step_output, with_history, write_result  # noqa: E402
from planlib import AUDIT_DIR, LOOP, PLAN_DIR, STUDY_MODEL, TLF_INDEX, TLF_PLAN  # noqa: E402

WORKFLOW = "tlf-planning"
PLAN_KINDS = ((STUDY_MODEL, "study-model"), (TLF_PLAN, "tlf-plan"), (TLF_INDEX, "tlf-plan-view"), ("tlf-plan.html", "tlf-plan-view"))


def main() -> None:
    step_input = read_input()
    resolved = step_output(step_input, "resolve-inputs")
    staged = step_output(step_input, "stage-inputs")
    gate = step_output(step_input, "check-plan")
    audit = step_output(step_input, "audit-plan")

    package = resolved.get("package") or {}
    if resolved.get("needsUpload") is True:
        uploaded = [
            {**item, "producedBy": {"workflow": WORKFLOW, "runId": os.environ.get("RUN_ID", ""), "step": "upload-inputs"}}
            for item in staged.get("inputFiles") or []
        ]
        package = replace_files(package, uploaded)

    study_check = step_output(step_input, "check-study")
    if study_check.get("failed") is True or gate.get("dataBlocked") is True:
        attached = [step_file("check-study", name, "tlf-plan-view", WORKFLOW) for name in ("study-check.html", "study-check.json")]
        if gate.get("dataBlocked") is True:
            attached += [publish_copy(PLAN_DIR / name, kind, WORKFLOW) for name, kind in PLAN_KINDS[:3]]
        reason = study_check.get("summary") if study_check.get("failed") is True else gate.get("summary")
        write_result({
            "outcome": "data-mismatch", "counts": gate.get("counts") or {}, "verdict": None, "problems": [reason],
            "summary": f"DATA MISMATCH: {reason}", "files": [entry for entry in attached if entry],
            "package": with_history(package, WORKFLOW, "data-mismatch"),
        })
        return

    if gate.get("needsFix") is True:
        problems = gate.get("problems") or []
        drafts = [entry for entry in (publish_copy(PLAN_DIR / name, kind, WORKFLOW) for name, kind in PLAN_KINDS[:3]) if entry]
        write_result({
            "outcome": "failed", "counts": gate.get("counts") or {}, "verdict": None, "problems": problems,
            "summary": f"FAILED: the plan gate still reports {len(problems)} problem(s) after {gate.get('attempt')} attempt(s), first: "
                       + (problems[0] if problems else "unknown") + ". The planner's files are attached.",
            "files": drafts, "package": with_history(package, WORKFLOW, "failed"),
        })
        return

    checked = [step_file("check-plan", name, kind, WORKFLOW) for name, kind in PLAN_KINDS]
    checked += [step_file("check-study", name, "tlf-plan-view", WORKFLOW) for name in ("study-check.html", "study-check.json")]
    audit_report = step_file("audit-plan", "coverage-report.md", "coverage-report", WORKFLOW) \
        or publish_copy(AUDIT_DIR / "coverage-report.md", "coverage-report", WORKFLOW)
    feedback = publish_copy(LOOP.review_feedback_path, f"review-feedback-{WORKFLOW}", WORKFLOW)
    files = [entry for entry in checked + [audit_report, feedback] if entry]
    counts = gate.get("counts") or {}
    verdict = audit.get("verdict")
    write_result({
        "outcome": "planned", "counts": counts, "verdict": verdict, "problems": [],
        "summary": f"PLANNED: {counts.get('tables', 0)} tables, {counts.get('listings', 0)} listings, {counts.get('figures', 0)} figures, "
                   f"{counts.get('flagged', 0)} flagged; critic verdict {verdict or 'n/a'}; approved by the statistician.",
        "files": files, "package": with_history(replace_files(package, files), WORKFLOW, "planned"),
    })


if __name__ == "__main__":
    run_main(main)
