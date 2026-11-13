"""Decide where this digitization run's protocol comes from.

Started by a parent workflow, the trigger carries a study `package`: its
protocol (and SAP, when there is one) go to `stage-inputs` as top-level `files`
(the runtime downloads them). Started by hand, there is no package and the run
goes to the upload step instead.

Result: { needsUpload, files, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, files_of_kind, read_input, run_main, write_result  # noqa: E402


def main() -> None:
    step_input = read_input()
    package = step_input.get("package")
    package = package if isinstance(package, dict) and package.get("files") else None

    if package is None:
        write_result({
            "needsUpload": True, "files": [], "package": {},
            "summary": "No study package: waiting for the protocol PDF (and optional SAP) to be uploaded.",
        })
        return

    protocols = files_of_kind(package, "protocol")
    if len(protocols) != 1:
        raise StepFailure(f"The study package needs exactly one protocol (kind protocol), it has {len(protocols)}.")
    files = protocols + files_of_kind(package, "sap")[:1]
    write_result({
        "needsUpload": False, "files": files, "package": package,
        "summary": f"Digitizing {protocols[0]['name']}" + (f" with the SAP {files[1]['name']} as context." if len(files) > 1 else "."),
    })


if __name__ == "__main__":
    run_main(main)
