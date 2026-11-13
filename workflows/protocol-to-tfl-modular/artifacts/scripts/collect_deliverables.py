"""Lift the deliverables to show from the final study package into top-level `files`.

The package ard-tfl-generation returned sits inside its result
(`steps.generate.output.package`); the runtime downloads only a step's top-level
`files`, and a step's viewer shows only what that step wrote to its /output. So
this step hands the files worth opening on as `files`, each tagged with `showAs`
(the name finish publishes it under - CORE reports of different standards share
a name), and finish, which follows, copies them into its /output.

Result: { files, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, step_output, write_result  # noqa: E402

# (kind, name in the package, name shown in the master run), in viewer order
SHOWN = (
    ("tfl", "tlf-viewer.html", "tlf-viewer.html"),
    ("tfl", "reconciliation.json", "reconciliation.json"),
    ("tfl", "accuracy.json", "accuracy.json"),
    ("tlf-plan-view", "study-check.html", "data-check-sdtm-vs-protocol.html"),
    ("usdm-view", "usdm-review.html", "usdm-review.html"),
    ("tlf-plan-view", "tlf-plan.html", "tlf-plan.html"),
    ("analysis-spec-view", "specs.html", "specs.html"),
    ("core-report-usdm", "core-report.html", "core-report-usdm.html"),
    ("core-report-sdtmig", "core-report.html", "core-report-sdtmig.html"),
    ("core-report-adamig", "core-report.html", "core-report-adamig.html"),
    ("adam-define", "define.xml", "adam-define.xml"),
)


def shown_files(package: dict) -> list[dict]:
    files = package.get("files") or []
    chosen = []
    for kind, name, show_as in SHOWN:
        match = next((entry for entry in files if entry.get("kind") == kind and entry.get("name") == name and entry.get("downloadUrl")), None)
        if match is not None:
            chosen.append({**match, "showAs": show_as})
    return chosen


def main() -> None:
    generated = step_output(read_input(), "generate").get("output") or {}
    package = generated.get("package")
    if isinstance(package, dict) is False or not package.get("files"):
        raise StepFailure("ard-tfl-generation returned no study package.")
    files = shown_files(package)
    if not files:
        raise StepFailure("The study package has none of the deliverables to show (no TLF viewer).")
    write_result({"files": files, "package": package,
                  "summary": f"Showing {len(files)} deliverable(s): " + ", ".join(entry["showAs"] for entry in files) + "."})


if __name__ == "__main__":
    run_main(main)
