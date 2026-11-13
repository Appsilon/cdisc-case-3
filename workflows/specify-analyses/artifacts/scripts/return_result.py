"""Close the specification run: publish the approved specs and hand the study package back.

outcome:
  specified  the gate passed and the statistician approved; publishes the files exactly
             as the gate checked them (check-specs' output): analysis-spec, ars
             (reporting-event.json), adam-spec, analysis-spec-view (specs.html) and the
             review feedback.
  failed     the gate still failed after the last attempt; publishes what the agent
             wrote, for a human to pick up, and leaves the package's specs as they were.

Result: { outcome, counts, summary, files, package }
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gate import publish_copy  # noqa: E402
from mfpkg import read_input, replace_files, run_main, step_file, step_output, with_history, write_result  # noqa: E402
from speclib import ADAM_SPEC, ANALYSIS_SPEC, LOOP, REPORTING_EVENT, SPECS_DIR  # noqa: E402

WORKFLOW = "specify-analyses"
SPEC_KINDS = ((ANALYSIS_SPEC, "analysis-spec"), (REPORTING_EVENT, "ars"), (ADAM_SPEC, "adam-spec"))


def main() -> None:
    step_input = read_input()
    resolved = step_output(step_input, "resolve-inputs")
    staged = step_output(step_input, "stage-inputs")
    gate = step_output(step_input, "check-specs")

    package = resolved.get("package") or {}
    if resolved.get("needsUpload") is True:
        uploaded = [{**item, "producedBy": {"workflow": WORKFLOW, "runId": os.environ.get("RUN_ID", ""), "step": "upload-inputs"}}
                    for item in staged.get("inputFiles") or []]
        package = replace_files(package, uploaded)

    if gate.get("needsFix") is True:
        problems = gate.get("problems") or []
        drafts = [entry for entry in (publish_copy(SPECS_DIR / name, kind, WORKFLOW) for name, kind in SPEC_KINDS) if entry]
        write_result({
            "outcome": "failed", "counts": gate.get("counts") or {}, "problems": problems,
            "summary": f"FAILED: the spec gate still reports {len(problems)} problem(s) after {gate.get('attempt')} attempt(s), first: "
                       + (problems[0] if problems else "unknown") + ". The agent's files are attached.",
            "files": drafts, "package": with_history(package, WORKFLOW, "failed"),
        })
        return

    checked = [step_file("check-specs", name, kind, WORKFLOW) for name, kind in SPEC_KINDS + (("specs.html", "analysis-spec-view"),)]
    feedback = publish_copy(LOOP.review_feedback_path, f"review-feedback-{WORKFLOW}", WORKFLOW)
    files = [entry for entry in checked + [feedback] if entry]
    counts = gate.get("counts") or {}
    write_result({
        "outcome": "specified", "counts": counts, "problems": [],
        "summary": f"SPECIFIED: {counts.get('analyses', 0)} analyses, ADaM spec of {', '.join(counts.get('datasets') or [])}, "
                   "ARS ReportingEvent schema-valid; approved by the statistician.",
        "files": files, "package": with_history(replace_files(package, files), WORKFLOW, "specified"),
    })


if __name__ == "__main__":
    run_main(main)
