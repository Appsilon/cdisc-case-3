"""Verify and stage the generation inputs where the agent and the executor read them.

Files arrive as top-level `files` (package or upload), already downloaded with
`localPath`. Each is sha256-verified and staged under
/workspace/ard-tfl-generation/inputs: ADaM as adam/<dataset>.xpt, the specs,
the plan and lineage.json by name; previous TLF programs go back to
/workspace/tlf-programs. adam-columns.json records what each ADaM dataset
holds, for the program tags to resolve against. Uploads carry no kind, so they
are classified by name.

Result: { inputFiles: [{name, downloadUrl, sha256, kind}], datasets, outputs, summary }
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, sha256_of, verify_files, write_result  # noqa: E402
from sdtminventory import sdtm_inventory  # noqa: E402
from tfllib import ADAM_COLUMNS_PATH, ADAM_DIR, INPUTS_DIR, PROGRAMS_DIR, WORK_DIR, planned_outputs  # noqa: E402

NAMED = {"analysis-spec.json": "analysis-spec", "reporting-event.json": "ars", "tlf-plan.json": "tlf-plan", "lineage.json": "lineage"}


def classify(entry: dict) -> str:
    if entry.get("kind"):
        return str(entry["kind"])
    name = str(entry.get("name", ""))
    if name.lower().endswith(".xpt"):
        return "adam"
    if name.endswith(".R"):
        return "tfl-program"
    return NAMED.get(name, "ignored")


def main() -> None:
    files = verify_files(read_input().get("files") or [])
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    ADAM_DIR.mkdir(parents=True)

    kinds = [(entry, classify(entry)) for entry in files]
    programs = [entry for entry, kind in kinds if kind == "tfl-program"]
    if programs:
        shutil.rmtree(PROGRAMS_DIR, ignore_errors=True)
        PROGRAMS_DIR.mkdir(parents=True)
    for entry, kind in kinds:
        if kind == "adam":
            shutil.copyfile(entry["localPath"], ADAM_DIR / entry["name"].lower())
        elif kind == "tfl-program":
            shutil.copyfile(entry["localPath"], PROGRAMS_DIR / entry["name"])
        elif entry["name"] in NAMED:
            shutil.copyfile(entry["localPath"], INPUTS_DIR / entry["name"])
    for required in ("analysis-spec.json", "reporting-event.json", "tlf-plan.json"):
        if (INPUTS_DIR / required).is_file() is False:
            raise StepFailure(f"{required} is required (the approved output of tlf-planning / analysis-specification).")

    inventory = sdtm_inventory(sorted(ADAM_DIR.glob("*.xpt")))
    unreadable = sorted(name for name, summary in inventory.items() if "error" in summary)
    if not inventory or unreadable:
        raise StepFailure("No readable ADaM datasets" + (f": {', '.join(unreadable)} could not be read." if unreadable else "."))
    ADAM_COLUMNS_PATH.write_text(json.dumps({name: summary["variables"] for name, summary in inventory.items()}, indent=2), encoding="utf-8")
    outputs = planned_outputs()
    if not outputs:
        raise StepFailure("No planned output has an analysis-spec entry; nothing to generate.")

    write_result({
        "inputFiles": [{"name": entry["name"], "downloadUrl": entry.get("downloadUrl"),
                        "sha256": entry.get("sha256") or sha256_of(Path(entry["localPath"])), "kind": kind}
                       for entry, kind in kinds if kind != "ignored"],
        "datasets": sorted(inventory),
        "outputs": sorted(outputs),
        "summary": f"Staged {len(inventory)} ADaM dataset(s) ({', '.join(sorted(inventory))}) for {len(outputs)} output(s)"
                   + (f"; {len(programs)} existing program(s) restored." if programs else "."),
    })


if __name__ == "__main__":
    run_main(main)
