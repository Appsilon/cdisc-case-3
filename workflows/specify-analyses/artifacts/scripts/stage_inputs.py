"""Verify and stage the specification inputs where the spec agent reads them.

Files arrive as top-level `files` (package or upload), already downloaded with
`localPath`. Each is sha256-verified and staged under
/workspace/specify-analyses/inputs: tlf-plan.json, study-model.json,
define.xml, sap/, usdm/, and sdtm-inventory.json (what the delivered SDTM
holds). With a change `request`, the previous specs go to specs/ and the request
becomes the first line of review-feedback.jsonl, as if a reviewer had asked for
it, so the agent revises them. Uploads carry no kind, so JSON is classified by content, datasets and
define.xml by extension, and a document is the SAP only when its name says so
('sap', 'statistical'); anything else is ignored.

Result: { inputFiles: [{name, downloadUrl, sha256, kind}], sdtmDomains, plannedOutputs, summary }
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, now_iso, read_input, run_main, sha256_of, verify_files, write_result  # noqa: E402
from sdtminventory import sdtm_inventory  # noqa: E402
from speclib import INPUTS_DIR, LOOP, SPECS_DIR, WORK_DIR, planned_tables  # noqa: E402

DATASET_SUFFIXES = (".xpt", ".sas7bdat")
SINGLE_FILES = {"tlf-plan": "tlf-plan.json", "study-model": "study-model.json", "sdtm-define": "define.xml"}
FOLDER_KINDS = ("sap", "usdm")
PREVIOUS_SPECS = {"analysis-spec": "analysis-spec.json", "adam-spec": "adam-spec.json", "ars": "reporting-event.json"}


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
    if re.search(r"(^|[^a-z])sap([^a-z]|$)", name) or "statistical" in name:
        return "sap"
    return "ignored"


def stage_change_request(request: str, kinds: list[tuple[dict, str]]) -> None:
    previous = {kind: entry for entry, kind in kinds if kind in PREVIOUS_SPECS}
    if len(previous) != len(PREVIOUS_SPECS):
        raise StepFailure("A change request needs the previous analysis-spec.json, adam-spec.json and reporting-event.json.")
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    for kind, entry in previous.items():
        shutil.copyfile(entry["localPath"], SPECS_DIR / PREVIOUS_SPECS[kind])
    line = {"skill": "tlf-analysis-spec", "iteration": 1, "comment": request, "source": "TLF review (upstream change)", "at": now_iso()}
    LOOP.review_feedback_path.write_text(json.dumps(line) + "\n", encoding="utf-8")


def main() -> None:
    step_input = read_input()
    request = str(step_input.get("request") or "").strip()
    files = verify_files(step_input.get("files") or [])
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    INPUTS_DIR.mkdir(parents=True)

    kinds = [(entry, classify(entry)) for entry in files]
    for kind, target in SINGLE_FILES.items():
        matches = [entry for entry, entry_kind in kinds if entry_kind == kind]
        if len(matches) > 1:
            raise StepFailure(f"Expected one {target}, got {len(matches)}: " + ", ".join(entry["name"] for entry in matches))
        if matches:
            shutil.copyfile(matches[0]["localPath"], INPUTS_DIR / target)
    for required in ("tlf-plan.json", "study-model.json"):
        if (INPUTS_DIR / required).is_file() is False:
            raise StepFailure(f"{required} is required (the approved output of plan-tlfs).")
    for entry, kind in kinds:
        if kind in FOLDER_KINDS:
            (INPUTS_DIR / kind).mkdir(exist_ok=True)
            shutil.copyfile(entry["localPath"], INPUTS_DIR / kind / entry["name"])

    if request:
        stage_change_request(request, kinds)

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
        "request": request,
        "summary": f"Staged the plan ({len(planned)} planned output(s)), the study model and an SDTM inventory of {len(inventory)} domain(s)"
                   + (", and the previous specs with the change request." if request else "."),
    })


if __name__ == "__main__":
    run_main(main)
