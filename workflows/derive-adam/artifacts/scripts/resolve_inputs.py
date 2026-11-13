"""Decide where this derivation's inputs come from.

Started by a parent workflow, the trigger carries a study `package`: its SDTM,
SDTM define, ADaM spec and - on a fix loop after a rejected ADaM validation -
the previous programs, lineage and CORE findings are handed to `stage-inputs`
as top-level `files`, which the runtime downloads. Started by hand, there is no
package and the run goes to the upload step instead.

Result: { needsUpload, files, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, files_of_kind, read_input, run_main, write_result  # noqa: E402

REQUIRED_KINDS = ("sdtm", "adam-spec")
CONTEXT_KINDS = ("sdtm-define", "analysis-spec")
# Present only when an ADaM validation sent the delivery back: the agent edits
# the programs that ran instead of starting over, guided by the findings.
FIX_KINDS = ("adam-program", "lineage", "core-dispositions-adamig", "core-report-adamig")


def main() -> None:
    step_input = read_input()
    package = step_input.get("package")
    package = package if isinstance(package, dict) and package.get("files") else None

    if package is None:
        write_result({
            "needsUpload": True,
            "files": [],
            "package": {},
            "summary": "No study package: waiting for the SDTM datasets and adam-spec.json to be uploaded.",
        })
        return

    missing = [kind for kind in REQUIRED_KINDS if not files_of_kind(package, kind)]
    if missing:
        raise StepFailure(
            "The study package lacks " + " and ".join(missing) + ". Kinds present: "
            + ", ".join(sorted({str(entry.get("kind")) for entry in package.get("files") or []}) or ["none"])
        )
    reports = [entry for entry in files_of_kind(package, "core-report-adamig") if entry.get("name") == "core-report.json"]
    lineage = [entry for entry in files_of_kind(package, "lineage") if entry.get("name") == "lineage.json"]
    fix_files = [entry for entry in files_of_kind(package, *FIX_KINDS) if entry.get("kind") not in ("core-report-adamig", "lineage")] + reports + lineage
    files = files_of_kind(package, *REQUIRED_KINDS, *CONTEXT_KINDS) + fix_files
    write_result({
        "needsUpload": False,
        "files": files,
        "package": package,
        "summary": (
            f"Deriving ADaM from {len(files_of_kind(package, 'sdtm'))} SDTM dataset(s)"
            + (f", fixing {len(files_of_kind(package, 'adam-program'))} existing program(s) against the last ADaM validation."
               if fix_files else ".")
        ),
    })


if __name__ == "__main__":
    run_main(main)
