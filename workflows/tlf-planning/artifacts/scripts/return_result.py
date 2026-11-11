"""Close the planning run: publish the approved plan and hand the study package back.

outcome:
  planned  the gate passed, the critic audited it and the statistician approved;
           publishes study-model, tlf-plan (json, index, html) and coverage-report.
  failed   the gate still failed after the last attempt; publishes what the
           planner wrote, for a human to pick up, and leaves the package's plan as it was.

Result: { outcome, counts, verdict, summary, files, package }
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, STEP_OUTPUTS_DIR, published_file, read_input, replace_files, run_main, step_output, with_history, write_result  # noqa: E402
from planlib import AUDIT_DIR, PLAN_DIR, REVIEW_FEEDBACK_PATH, STUDY_MODEL, TLF_INDEX, TLF_PLAN  # noqa: E402

WORKFLOW = "tlf-planning"
PLAN_KINDS = ((STUDY_MODEL, "study-model"), (TLF_PLAN, "tlf-plan"), (TLF_INDEX, "tlf-plan"))


def publish(source: Path, kind: str) -> dict | None:
    if source.is_file() is False:
        return None
    target = OUTPUT_DIR / source.name
    shutil.copyfile(source, target)
    return published_file(target, kind, WORKFLOW)


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

    plan_files = [entry for entry in (publish(PLAN_DIR / name, kind) for name, kind in PLAN_KINDS) if entry]
    if gate.get("needsFix") is True:
        problems = gate.get("problems") or []
        write_result({
            "outcome": "failed", "counts": gate.get("counts") or {}, "verdict": None, "problems": problems,
            "summary": f"FAILED: the plan gate still reports {len(problems)} problem(s) after {gate.get('attempt')} attempt(s), first: "
                       + (problems[0] if problems else "unknown") + ". The planner's files are attached.",
            "files": plan_files, "package": with_history(package, WORKFLOW, "failed"),
        })
        return

    extra = [entry for entry in [
        publish(AUDIT_DIR / "coverage-report.md", "coverage-report"),
        publish(REVIEW_FEEDBACK_PATH, "review-feedback"),
    ] if entry]
    rendered = publish(STEP_OUTPUTS_DIR / "check-plan" / "tlf-plan.html", "tlf-plan")
    files = plan_files + ([rendered] if rendered else []) + extra
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
