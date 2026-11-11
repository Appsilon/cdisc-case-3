"""Verify and stage the specification inputs where the spec agent reads them.

Files arrive as top-level `files` (package or upload), already downloaded with
`localPath`. Each is sha256-verified and staged under
/workspace/analysis-specification/inputs: tlf-plan.json, study-model.json,
define.xml, sap/, usdm/, and sdtm-inventory.json (what the delivered SDTM
holds). Uploads carry no kind, so JSON is classified by content and the rest
by extension.

Result: { inputFiles: [{name, downloadUrl, sha256, kind}], sdtmDomains, plannedOutputs, summary }
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, sha256_of, verify_files, write_result  # noqa: E402
from sdtminventory import sdtm_inventory  # noqa: E402
from speclib import INPUTS_DIR, WORK_DIR, planned_tables, reset_attempts  # noqa: E402

DATASET_SUFFIXES = (".xpt", ".sas7bdat")
SINGLE_FILES = {"tlf-plan": "tlf-plan.json", "study-model": "study-model.json", "sdtm-define": "define.xml"}
FOLDER_KINDS = ("sap", "usdm")


def sniff_json(path: Path) -> str:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "ignored"
    if isinstance(document, list) and document and isinstance(document[0], dict) and "candidate_id" in document[0]:
        return "tlf-plan"
    if isinstance(document, dict) and "objectives" in document and "endpoints" in document:
        return "study-model"
    if isinstance(document, dict) and ("usdmVersion" in document or "study" in document):
        return "usdm"
    return "ignored"


def classify(entry: dict) -> str:
    if entry.get("kind"):
        return str(entry["kind"])
    name = str(entry.get("name", "")).lower()
    if name.endswith(DATASET_SUFFIXES):
        return "sdtm"
    if name.endswith(".xml"):
        return "sdtm-define"
    if name.endswith(".json"):
        return sniff_json(Path(entry["localPath"]))
    return "sap"


def main() -> None:
    files = verify_files(read_input().get("files") or [])
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    INPUTS_DIR.mkdir(parents=True)
    reset_attempts()

    kinds = [(entry, classify(entry)) for entry in files]
    for kind, target in SINGLE_FILES.items():
        matches = [entry for entry, entry_kind in kinds if entry_kind == kind]
        if len(matches) > 1:
            raise StepFailure(f"Expected one {target}, got {len(matches)}: " + ", ".join(entry["name"] for entry in matches))
        if matches:
            shutil.copyfile(matches[0]["localPath"], INPUTS_DIR / target)
    for required in ("tlf-plan.json", "study-model.json"):
        if (INPUTS_DIR / required).is_file() is False:
            raise StepFailure(f"{required} is required (the approved output of tlf-planning).")
    for entry, kind in kinds:
        if kind in FOLDER_KINDS:
            (INPUTS_DIR / kind).mkdir(exist_ok=True)
            shutil.copyfile(entry["localPath"], INPUTS_DIR / kind / entry["name"])

    inventory = sdtm_inventory([Path(entry["localPath"]) for entry, kind in kinds if kind == "sdtm"])
    (INPUTS_DIR / "sdtm-inventory.json").write_text(json.dumps({"domains": inventory}, indent=2), encoding="utf-8")
    planned = planned_tables(json.loads((INPUTS_DIR / "tlf-plan.json").read_text(encoding="utf-8")))
    if not planned:
        raise StepFailure("tlf-plan.json has no planned, numbered outputs to specify.")

    write_result({
        "inputFiles": [{"name": entry["name"], "downloadUrl": entry.get("downloadUrl"),
                        "sha256": entry.get("sha256") or sha256_of(Path(entry["localPath"])), "kind": kind}
                       for entry, kind in kinds if kind != "ignored"],
        "sdtmDomains": sorted(inventory),
        "plannedOutputs": len(planned),
        "summary": f"Staged the plan ({len(planned)} planned output(s)), the study model and an SDTM inventory of {len(inventory)} domain(s).",
    })


if __name__ == "__main__":
    run_main(main)
