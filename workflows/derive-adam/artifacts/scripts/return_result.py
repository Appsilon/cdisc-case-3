"""Close the derivation: publish what was derived and hand the study package back.

outcome:
  derived  programs ran with clean logs, lineage gate passed, define generated;
           publishes adam (.xpt), adam-program (.R), adam-log, adam-define, and under
           kind lineage: lineage.json and population-counts.json.
  failed   the gates still failed after the last attempt; publishes the programs
           and logs for a human to pick up, and leaves the package's data as it was.

Result: { outcome, attempts, problems, datasets, summary, files, package }
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adamlib import attempts  # noqa: E402
from mfpkg import (  # noqa: E402
    STEP_OUTPUTS_DIR, read_input, replace_files, run_main, step_file, step_output, with_history, write_result,
)

WORKFLOW = "derive-adam"


def folder_files(step_id: str, folder: str, suffix: str, kind: str) -> list[dict]:
    directory = STEP_OUTPUTS_DIR / step_id / folder
    paths = sorted(directory.glob(f"*{suffix}")) if directory.is_dir() else []
    return [entry for entry in (step_file(step_id, f"{folder}/{path.name}", kind, WORKFLOW) for path in paths) if entry]


def main() -> None:
    step_input = read_input()
    resolved = step_output(step_input, "resolve-inputs")
    staged = step_output(step_input, "stage-inputs")
    executed = step_output(step_input, "execute-programs")
    lineage_gate = step_output(step_input, "check-lineage")
    if executed.get("needsFix") is True:
        failed_gate = executed
    elif lineage_gate.get("needsFix") is True:
        failed_gate = lineage_gate
    else:
        failed_gate = None

    package = resolved.get("package") or {}
    if resolved.get("needsUpload") is True:
        uploaded = [
            {**item, "producedBy": {"workflow": WORKFLOW, "runId": os.environ.get("RUN_ID", ""), "step": "upload-inputs"}}
            for item in staged.get("inputFiles") or []
        ]
        package = replace_files(package, uploaded)

    programs = folder_files("execute-programs", "programs", ".R", "adam-program")
    logs = folder_files("execute-programs", "logs", ".log", "adam-log")
    if failed_gate is not None:
        problems = failed_gate.get("problems") or []
        files = programs + logs
        package = with_history(package, WORKFLOW, "failed")
        summary = (f"FAILED after {attempts()} attempt(s): {len(problems)} problem(s) remain, first: "
                   + (problems[0] if problems else "unknown") + ". Programs and logs are attached.")
        write_result({"outcome": "failed", "attempts": attempts(), "problems": problems, "datasets": executed.get("datasets") or [],
                      "summary": summary, "files": files, "package": package})
        return

    datasets = folder_files("execute-programs", "adam", ".xpt", "adam")
    singles = [step_file("check-lineage", "lineage.json", "lineage", WORKFLOW), step_file("check-lineage", "population-counts.json", "lineage", WORKFLOW),
               step_file("generate-define", "define.xml", "adam-define", WORKFLOW)]
    files = datasets + programs + logs + [entry for entry in singles if entry]
    package = with_history(replace_files(package, files), WORKFLOW, "derived")
    summary = (f"DERIVED in {attempts()} attempt(s): " + ", ".join(f"{item['dataset']} ({item['rows']} rows)" for item in executed.get("datasets") or [])
               + f". {(lineage_gate.get('counts') or {}).get('variables', 0)} variable(s) traced to program lines; define.xml generated.")
    write_result({"outcome": "derived", "attempts": attempts(), "problems": [], "datasets": executed.get("datasets") or [],
                  "summary": summary, "files": files, "package": package})


if __name__ == "__main__":
    run_main(main)
