"""Close the generation run: publish the ARD, the displays and the programs, and hand the study package back.

outcome:
  generated        programs ran, every displayed number reconciles with the ARD, and the
                   reviewer approved; publishes ard, tfl (displays + tlf-viewer.html +
                   reconciliation.json + accuracy.json), tfl-program, tfl-log.
  upstream_change  the reviewer says the specs must change (comment in `request`); publishes
                   the current programs and outputs for reference, package unchanged otherwise.
  failed           the gates still failed after the last attempt; publishes the programs and
                   logs for a human to pick up.

Result: { outcome, outputs, request, summary, files, package }
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import STEP_OUTPUTS_DIR, read_input, replace_files, run_main, step_file, step_output, with_history, write_result  # noqa: E402
from tfllib import LOOP  # noqa: E402

WORKFLOW = "generate-ard-tlfs"


def folder_files(step_id: str, folder: str, suffixes: tuple[str, ...], kind: str) -> list[dict]:
    directory = STEP_OUTPUTS_DIR / step_id / folder
    paths = sorted(path for path in directory.iterdir() if path.suffix in suffixes) if directory.is_dir() else []
    return [entry for entry in (step_file(step_id, f"{folder}/{path.name}", kind, WORKFLOW) for path in paths) if entry]


def main() -> None:
    step_input = read_input()
    resolved = step_output(step_input, "resolve-inputs")
    staged = step_output(step_input, "stage-inputs")
    executed = step_output(step_input, "execute-programs")
    reconciled = step_output(step_input, "reconcile")
    review = step_output(step_input, "review-tlfs")

    package = resolved.get("package") or {}
    if resolved.get("needsUpload") is True:
        uploaded = [{**item, "producedBy": {"workflow": WORKFLOW, "runId": os.environ.get("RUN_ID", ""), "step": "upload-inputs"}}
                    for item in staged.get("inputFiles") or []]
        package = replace_files(package, uploaded)

    programs = folder_files("execute-programs", "programs", (".R",), "tfl-program")
    logs = folder_files("execute-programs", "logs", (".log",), "tfl-log")
    failed_gate = executed if executed.get("needsFix") is True else (reconciled if reconciled.get("needsFix") is True else None)
    if failed_gate is not None:
        problems = failed_gate.get("problems") or []
        write_result({"outcome": "failed", "outputs": [], "request": None, "problems": problems,
                      "summary": f"FAILED after {LOOP.attempts()} attempt(s): {len(problems)} problem(s), first: "
                                 + (problems[0] if problems else "unknown") + ". Programs and logs are attached.",
                      "files": programs + logs, "package": with_history(package, WORKFLOW, "failed")})
        return

    ard = folder_files("execute-programs", "ard", (".json",), "ard")
    displays = folder_files("execute-programs", "tfl", (".html", ".png"), "tfl")
    reports = [entry for entry in (step_file("reconcile", name, "tfl", WORKFLOW) for name in ("tlf-viewer.html", "reconciliation.json", "accuracy.json")) if entry]
    outputs = [item.get("id") for item in executed.get("outputs") or []]
    if review.get("verdict") == "spec-change":
        request = str(review.get("reviewerComment") or review.get("comment") or "").strip()
        write_result({"outcome": "upstream_change", "outputs": outputs, "request": request, "problems": [],
                      "summary": f"UPSTREAM CHANGE requested by the reviewer: {request[:300]}",
                      "files": reports + programs, "package": with_history(package, WORKFLOW, "upstream_change")})
        return

    files = ard + displays + reports + programs + logs
    coverage = (reconciled.get("accuracy") or {}).get("coverage") or {}
    write_result({"outcome": "generated", "outputs": outputs, "request": None, "problems": [],
                  "summary": f"GENERATED {len(outputs)} output(s) in {LOOP.attempts()} attempt(s): ARD + display each, "
                             f"{reconciled.get('checked', 0)} displayed numbers reconciled with the ARD, "
                             f"{coverage.get('recomputed', 0)} of {coverage.get('statistics', 0)} ARD statistics recomputed from ADaM; "
                             "approved. Open tlf-viewer.html.",
                  "files": files, "package": with_history(replace_files(package, files), WORKFLOW, "generated")})


if __name__ == "__main__":
    run_main(main)
