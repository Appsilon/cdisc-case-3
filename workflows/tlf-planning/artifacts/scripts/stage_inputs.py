"""Verify and stage the planning inputs where the planner agent reads them.

Files arrive as top-level `files` (from the study package or the upload),
already downloaded with `localPath`. Each is sha256-verified and staged under
/workspace/tlf-planning/inputs: the USDM as usdm.json, documents by kind in
sap/, protocol/, shells/. The delivered SDTM is summarised in
sdtm-inventory.json - per domain the record count, the variables and the
distinct category / test / parameter codes - so feasibility is decided on what
the data holds (QS split into QSPH + QSSL says nothing about which instrument
is in it), not on file names. The DM / EX / TS / TA columns check-study compares
with the USDM go to sdtm-study-facts.json. Uploads carry no kind, so they are classified by
content (USDM JSON) and name (.xml = SDTM define, carried on for CORE; sap /
shell in the file name; otherwise protocol).

Result: { inputFiles: [{name, downloadUrl, sha256, kind}], sdtmDomains, summary }
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, sha256_of, verify_files, write_result  # noqa: E402
from sdtminventory import sdtm_inventory  # noqa: E402
from studycheck import study_facts  # noqa: E402
from planlib import INPUTS_DIR, WORK_DIR  # noqa: E402

DATASET_SUFFIXES = (".xpt", ".sas7bdat")
DOCUMENT_KINDS = ("sap", "protocol", "shells")


def is_usdm(path: Path) -> bool:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if isinstance(document, dict) is False:
        return False
    study = document.get("study")
    return "usdmVersion" in document or (isinstance(study, dict) and "versions" in study)


def classify(entry: dict) -> str:
    if entry.get("kind"):
        return str(entry["kind"])
    name = str(entry.get("name", "")).lower()
    if name.endswith(DATASET_SUFFIXES):
        return "sdtm"
    if name.endswith(".xml"):
        return "sdtm-define"
    if name.endswith(".json"):
        return "usdm" if is_usdm(Path(entry["localPath"])) else "ignored"
    if re.search(r"(^|[^a-z])sap([^a-z]|$)", name) or "statistical" in name:
        return "sap"
    if "shell" in name or "mock" in name:
        return "shells"
    return "protocol"


def main() -> None:
    step_input = read_input()
    files = verify_files(step_input.get("files") or [])

    shutil.rmtree(WORK_DIR, ignore_errors=True)
    INPUTS_DIR.mkdir(parents=True)

    kinds = [(entry, classify(entry)) for entry in files]
    usdm = [entry for entry, kind in kinds if kind == "usdm"]
    if len(usdm) != 1:
        raise StepFailure(f"Expected exactly one USDM study-definition JSON, got {len(usdm)}: "
                          + (", ".join(entry["name"] for entry in usdm) or "none (a USDM JSON has usdmVersion or study.versions)"))
    shutil.copyfile(usdm[0]["localPath"], INPUTS_DIR / "usdm.json")
    for entry, kind in kinds:
        if kind in DOCUMENT_KINDS:
            (INPUTS_DIR / kind).mkdir(exist_ok=True)
            shutil.copyfile(entry["localPath"], INPUTS_DIR / kind / entry["name"])

    sdtm_paths = [Path(entry["localPath"]) for entry, kind in kinds if kind == "sdtm"]
    inventory = sdtm_inventory(sdtm_paths)
    (INPUTS_DIR / "sdtm-study-facts.json").write_text(json.dumps({"sdtmFiles": len(sdtm_paths), "facts": study_facts(sdtm_paths)}),
                                                      encoding="utf-8")
    (INPUTS_DIR / "sdtm-inventory.json").write_text(json.dumps({"domains": inventory}, indent=2), encoding="utf-8")
    domains = sorted(inventory)
    unreadable = sorted(domain for domain, summary in inventory.items() if "error" in summary)

    input_files = [
        {"name": entry["name"], "downloadUrl": entry.get("downloadUrl"), "sha256": entry.get("sha256") or sha256_of(Path(entry["localPath"])),
         "kind": kind}
        for entry, kind in kinds if kind != "ignored"
    ]
    documents = [f"{entry['name']} ({kind})" for entry, kind in kinds if kind in DOCUMENT_KINDS]
    write_result({
        "inputFiles": input_files,
        "sdtmDomains": domains,
        "summary": f"Staged {usdm[0]['name']}" + (f", {', '.join(documents)}" if documents else "")
                   + f"; SDTM inventory of {len(domains)} domain(s) for feasibility"
                   + (f" ({len(unreadable)} unreadable: {', '.join(unreadable)})." if unreadable else "."),
    })


if __name__ == "__main__":
    run_main(main)
