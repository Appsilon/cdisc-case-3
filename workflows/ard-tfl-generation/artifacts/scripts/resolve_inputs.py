"""Decide where this generation run's inputs come from.

Started by a parent workflow, the trigger carries a study `package`: its ADaM
datasets, the approved specs (analysis-spec.json, reporting-event.json), the
plan, the ADaM lineage and - on a review round driven by a parent - the
previous TLF programs go to `stage-inputs` as top-level `files`. Started by
hand, there is no package and the run goes to the upload step instead.

Result: { needsUpload, files, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, files_of_kind, read_input, run_main, write_result  # noqa: E402

NAMED = (("analysis-spec", "analysis-spec.json"), ("ars", "reporting-event.json"), ("tlf-plan", "tlf-plan.json"))
OPTIONAL_KINDS = ("lineage", "tfl-program")


def main() -> None:
    step_input = read_input()
    package = step_input.get("package")
    package = package if isinstance(package, dict) and package.get("files") else None
    if package is None:
        write_result({"needsUpload": True, "files": [], "package": {},
                      "summary": "No study package: waiting for the ADaM datasets and the approved specs to be uploaded."})
        return

    named = [[entry for entry in files_of_kind(package, kind) if entry.get("name") == name][:1] for kind, name in NAMED]
    adam = files_of_kind(package, "adam")
    missing = [name for (kind, name), found in zip(NAMED, named) if not found] + (["ADaM datasets (kind adam)"] if not adam else [])
    if missing:
        raise StepFailure("The study package lacks " + ", ".join(missing) + ". Run analysis-specification and adam-derivation first.")
    files = adam + [entry for found in named for entry in found] + files_of_kind(package, *OPTIONAL_KINDS)
    write_result({"needsUpload": False, "files": files, "package": package,
                  "summary": f"Generating from {len(adam)} ADaM dataset(s) and the approved specs"
                             + (", continuing from existing TLF programs." if files_of_kind(package, "tfl-program") else ".")})


if __name__ == "__main__":
    run_main(main)
