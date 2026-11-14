"""Lift the deliverables to show from the final study package into top-level `files`.

The package trace-deliverables returned (generate-ard-tlfs's package plus the
traceability explorer) sits inside its result
(`steps.trace-deliverables.output.package`). The explorer is not a gate: when
trace-deliverables did not finish, generate-ard-tlfs's package is used and its
TLF viewer shown instead, and the summary says so. The runtime downloads only a
step's top-level `files`, and a step's viewer shows only what that step wrote to
its /output. So
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

EXPLORER = ("traceability", "traceability-explorer.html", "traceability-explorer.html")
VIEWER = ("tfl", "tlf-viewer.html", "tlf-viewer.html")
# (kind, name in the package, name shown in the master run), in viewer order, after the explorer (or the viewer)
SHOWN = (
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


def shown_files(package: dict, first: tuple[str, str, str]) -> list[dict]:
    files = package.get("files") or []
    chosen = []
    for kind, name, show_as in (first,) + SHOWN:
        match = next((entry for entry in files if entry.get("kind") == kind and entry.get("name") == name and entry.get("downloadUrl")), None)
        if match is not None:
            chosen.append({**match, "showAs": show_as})
    return chosen


def main() -> None:
    step_input = read_input()
    traced = step_output(step_input, "trace-deliverables").get("output") or {}
    package, first, note = traced.get("package"), EXPLORER, ""
    if isinstance(package, dict) is False or len(package.get("files") or []) == 0:
        package = (step_output(step_input, "generate-ard-tlfs").get("output") or {}).get("package")
        error = step_output(step_input, "trace-deliverables").get("error") or "it returned no study package"
        first, note = VIEWER, f" No traceability explorer: trace-deliverables did not finish ({error}); showing the TLF viewer instead."
    if isinstance(package, dict) is False or len(package.get("files") or []) == 0:
        raise StepFailure("Neither trace-deliverables nor generate-ard-tlfs returned a study package.")
    files = shown_files(package, first)
    if len(files) == 0 or files[0]["showAs"] != first[2]:
        raise StepFailure(f"The study package has no {first[2]} to show.")
    write_result({"files": files, "package": package,
                  "summary": f"Showing {len(files)} deliverable(s): " + ", ".join(entry["showAs"] for entry in files) + "." + note})


if __name__ == "__main__":
    run_main(main)
