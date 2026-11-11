"""Close the specification run: publish the approved specs and hand the study package back.

outcome:
  specified  the gate passed and the statistician approved; publishes
             analysis-spec, ars (reporting-event.json) and adam-spec (+ specs.html).
  failed     the gate still failed after the last attempt; publishes what the
             agent wrote, for a human to pick up, and leaves the package's specs as they were.

Result: { outcome, counts, summary, files, package }
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import (  # noqa: E402
    OUTPUT_DIR, STEP_OUTPUTS_DIR, published_file, read_input, replace_files, run_main, step_output, with_history, write_result,
)
from speclib import ADAM_SPEC, ANALYSIS_SPEC, REPORTING_EVENT, REVIEW_FEEDBACK_PATH, SPECS_DIR  # noqa: E402

WORKFLOW = "analysis-specification"
SPEC_KINDS = ((ANALYSIS_SPEC, "analysis-spec"), (REPORTING_EVENT, "ars"), (ADAM_SPEC, "adam-spec"))


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
    gate = step_output(step_input, "check-specs")

    package = resolved.get("package") or {}
    if resolved.get("needsUpload") is True:
        uploaded = [{**item, "producedBy": {"workflow": WORKFLOW, "runId": os.environ.get("RUN_ID", ""), "step": "upload-inputs"}}
                    for item in staged.get("inputFiles") or []]
        package = replace_files(package, uploaded)

    spec_files = [entry for entry in (publish(SPECS_DIR / name, kind) for name, kind in SPEC_KINDS) if entry]
    if gate.get("needsFix") is True:
        problems = gate.get("problems") or []
        write_result({
            "outcome": "failed", "counts": gate.get("counts") or {}, "problems": problems,
            "summary": f"FAILED: the spec gate still reports {len(problems)} problem(s) after {gate.get('attempt')} attempt(s), first: "
                       + (problems[0] if problems else "unknown") + ". The agent's files are attached.",
            "files": spec_files, "package": with_history(package, WORKFLOW, "failed"),
        })
        return

    extra = [entry for entry in (publish(STEP_OUTPUTS_DIR / "check-specs" / "specs.html", "analysis-spec"),
                                 publish(REVIEW_FEEDBACK_PATH, f"review-feedback-{WORKFLOW}")) if entry]
    files = spec_files + extra
    counts = gate.get("counts") or {}
    write_result({
        "outcome": "specified", "counts": counts, "problems": [],
        "summary": f"SPECIFIED: {counts.get('analyses', 0)} analyses, ADaM spec of {', '.join(counts.get('datasets') or [])}, "
                   "ARS ReportingEvent schema-valid; approved by the statistician.",
        "files": files, "package": with_history(replace_files(package, files), WORKFLOW, "specified"),
    })


if __name__ == "__main__":
    run_main(main)
