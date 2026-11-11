"""Decide where this specification run's inputs come from.

Started by a parent workflow, the trigger carries a study `package`: its
approved plan (tlf-plan.json), study model, SDTM (for the inventory) and
optional SAP / USDM / SDTM define go to `stage-inputs` as top-level `files`.
With a change `request` (a TLF review asked for a different analysis), the
package's previous specs go too, so the agent revises them instead of starting
over. Started by hand, there is no package and the run goes to the upload step.

Result: { needsUpload, files, package, request, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, files_of_kind, read_input, run_main, write_result  # noqa: E402

CONTEXT_KINDS = ("sdtm", "sdtm-define", "sap", "usdm")
PREVIOUS_SPECS = {"analysis-spec": "analysis-spec.json", "adam-spec": "adam-spec.json", "ars": "reporting-event.json"}


def main() -> None:
    step_input = read_input()
    package = step_input.get("package")
    package = package if isinstance(package, dict) and package.get("files") else None
    request = str(step_input.get("request") or "").strip()

    if package is None and request:
        raise StepFailure("A change request needs the study package that holds the specs to change.")
    if package is None:
        write_result({"needsUpload": True, "files": [], "package": {},
                      "summary": "No study package: waiting for tlf-plan.json, study-model.json and the SDTM to be uploaded."})
        return

    plans = [entry for entry in files_of_kind(package, "tlf-plan") if entry.get("name") == "tlf-plan.json"]
    models = files_of_kind(package, "study-model")
    if not plans or not models:
        raise StepFailure("The study package lacks an approved plan (tlf-plan.json, kind tlf-plan) and study model (kind study-model). "
                          "Run tlf-planning first.")
    files = plans[:1] + models[:1] + files_of_kind(package, *CONTEXT_KINDS)
    if request:
        previous = [entry for kind, name in PREVIOUS_SPECS.items() for entry in files_of_kind(package, kind) if entry.get("name") == name]
        missing = sorted(set(PREVIOUS_SPECS.values()) - {entry["name"] for entry in previous})
        if missing:
            raise StepFailure(f"A change request revises existing specs, but the package lacks {', '.join(missing)}.")
        files += previous
    sdtm = len(files_of_kind(package, "sdtm"))
    summary = (f"Revising the approved specs for a change request: {request[:200]}" if request else
               f"Specifying from the approved plan with {sdtm} SDTM dataset(s)" + (" and no SDTM (sdtm_source cannot be checked)." if sdtm == 0 else "."))
    write_result({"needsUpload": False, "files": files, "package": package, "request": request, "summary": summary})


if __name__ == "__main__":
    run_main(main)
