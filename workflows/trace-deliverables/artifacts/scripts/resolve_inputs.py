"""Pick the files the traceability explorer reads out of the study package.

The runtime downloads only a step's top-level `files`, so this step lists them:
every kind the explorer links (ADaM data, programs and lineage; specs, plan and
ARS; USDM and its citations; ARD, displays, TLF programs; CORE reports and
dispositions; the SDTM define.xml for column labels). The SDTM datasets, the
protocol and SAP PDFs, the CORE spreadsheets and the TLF viewer are left out:
the explorer does not read them, and the SDTM alone is most of the package's size.

Result: { files, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, write_result  # noqa: E402

KINDS = ("adam", "adam-program", "adam-spec", "lineage", "analysis-spec", "ars", "tlf-plan", "usdm", "usdm-citations",
         "ard", "tfl", "tfl-program", "sdtm-define",
         "core-report-usdm", "core-report-sdtmig", "core-report-adamig",
         "core-dispositions-usdm", "core-dispositions-sdtmig", "core-dispositions-adamig")
SKIPPED_NAMES = ("tlf-viewer.html",)
CORE_REPORT_NAME = "core-report.json"


def wanted(entry: dict) -> bool:
    kind, name = str(entry.get("kind") or ""), str(entry.get("name") or "")
    if kind not in KINDS or name in SKIPPED_NAMES or not entry.get("downloadUrl"):
        return False
    return kind.startswith("core-report-") is False or name == CORE_REPORT_NAME


def main() -> None:
    package = read_input().get("package")
    if isinstance(package, dict) is False or len(package.get("files") or []) == 0:
        raise StepFailure("No study package in the trigger: start trace-deliverables with the package a protocol-to-tlfs run "
                          "(or generate-ard-tlfs) produced.")
    files = [entry for entry in package["files"] if wanted(entry)]
    kinds = {entry["kind"] for entry in files}
    missing = [kind for kind in ("lineage", "ard", "tfl", "tfl-program") if kind not in kinds]
    if len(missing) > 0:
        raise StepFailure("The study package has no " + ", ".join(missing) + ": run derive-adam and generate-ard-tlfs first.")
    write_result({"files": files, "package": package,
                  "summary": f"Tracing {len(files)} file(s) of {len(kinds)} kind(s) from the study package."})


if __name__ == "__main__":
    run_main(main)
