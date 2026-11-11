"""Decide where this planning run's inputs come from.

Started by a parent workflow, the trigger carries a study `package`: its USDM
and optional SAP / protocol / shells / SDTM go to `stage-inputs` as top-level
`files` (the runtime downloads them; SDTM feeds the feasibility inventory).
Started by hand, there is no package and the run goes to the upload step instead.

Result: { needsUpload, files, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, files_of_kind, read_input, run_main, write_result  # noqa: E402

CONTEXT_KINDS = ("sap", "protocol", "shells", "sdtm")


def main() -> None:
    step_input = read_input()
    package = step_input.get("package")
    package = package if isinstance(package, dict) and package.get("files") else None

    if package is None:
        write_result({
            "needsUpload": True,
            "files": [],
            "package": {},
            "summary": "No study package: waiting for the USDM JSON (and optional SAP, protocol, shells, SDTM) to be uploaded.",
        })
        return

    if not files_of_kind(package, "usdm"):
        hint = " Run protocol-digitization first to turn the protocol into USDM." if files_of_kind(package, "protocol") else ""
        raise StepFailure("The study package has no USDM (kind usdm)." + hint)
    files = files_of_kind(package, "usdm", *CONTEXT_KINDS)
    sdtm = len(files_of_kind(package, "sdtm"))
    write_result({
        "needsUpload": False,
        "files": files,
        "package": package,
        "summary": f"Planning from {files[0]['name']} with {len(files) - 1 - sdtm} context document(s) and "
                   + (f"{sdtm} delivered SDTM dataset(s)." if sdtm else "no SDTM delivered yet (feasibility not checked)."),
    })


if __name__ == "__main__":
    run_main(main)
