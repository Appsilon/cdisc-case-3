"""Verify and stage the planning inputs where the planner agent reads them.

Files arrive as top-level `files` (from the study package or the upload),
already downloaded with `localPath`. Each is sha256-verified and staged under
/workspace/tlf-planning/inputs: the USDM as usdm.json, documents by kind in
sap/, protocol/, shells/. The delivered SDTM is summarised in
sdtm-inventory.json - per domain the record count, the variables and the
distinct category / test / parameter codes - so feasibility is decided on what
the data holds (QS split into QSPH + QSSL says nothing about which instrument
is in it), not on file names. Uploads carry no kind, so they are classified by
content (USDM JSON) and name (sap / shell in the file name, otherwise protocol).

Result: { inputFiles: [{name, downloadUrl, sha256, kind}], sdtmDomains, summary }
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, sha256_of, verify_files, write_result  # noqa: E402
from planlib import INPUTS_DIR, WORK_DIR, reset_attempts  # noqa: E402

DATASET_SUFFIXES = (".xpt", ".sas7bdat")
DOCUMENT_KINDS = ("sap", "protocol", "shells")
MAX_VALUES = 80
# Reads each dataset with haven (the image's R) and writes the inventory as JSON.
INVENTORY_R = r'''
arguments <- commandArgs(TRUE)
output <- arguments[1]
paths <- arguments[-1]
code_suffixes <- c("CAT", "SCAT", "TESTCD", "TEST", "PARMCD", "PARM", "DECOD")
inventory <- list()
for (path in paths) {
  domain <- toupper(tools::file_path_sans_ext(basename(path)))
  inventory[[domain]] <- tryCatch({
    data <- if (grepl("\\.xpt$", path, ignore.case = TRUE)) haven::read_xpt(path) else haven::read_sas(path)
    columns <- names(data)
    coded <- columns[nchar(columns) > 2 & substring(columns, 3) %in% code_suffixes & !(columns %in% c("DOMAIN"))]
    values <- lapply(coded, function(column) {
      distinct <- sort(unique(as.character(data[[column]])))
      distinct <- distinct[!is.na(distinct) & distinct != ""]
      list(count = length(distinct), values = I(head(distinct, MAX_VALUES)))
    })
    names(values) <- coded
    list(records = nrow(data), variables = I(columns), codes = values)
  }, error = function(problem) list(error = conditionMessage(problem)))
}
jsonlite::write_json(inventory, output, auto_unbox = TRUE, pretty = TRUE)
'''.replace("MAX_VALUES", str(MAX_VALUES))


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
    if name.endswith(".json"):
        return "usdm" if is_usdm(Path(entry["localPath"])) else "ignored"
    if "sap" in name or "statistical" in name:
        return "sap"
    if "shell" in name or "mock" in name:
        return "shells"
    return "protocol"


def sdtm_inventory(paths: list[Path]) -> dict:
    if not paths:
        return {}
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "inventory.json"
        program = Path(temporary) / "inventory.R"
        program.write_text(INVENTORY_R, encoding="utf-8")
        completed = subprocess.run(["Rscript", "--vanilla", str(program), str(target), *map(str, paths)],
                                   capture_output=True, text=True)
        if completed.returncode != 0 or target.is_file() is False:
            raise StepFailure("Could not read the SDTM datasets for the feasibility inventory: " + completed.stderr.strip()[-800:])
        return json.loads(target.read_text(encoding="utf-8"))


def main() -> None:
    step_input = read_input()
    files = verify_files(step_input.get("files") or [])

    shutil.rmtree(WORK_DIR, ignore_errors=True)
    INPUTS_DIR.mkdir(parents=True)
    reset_attempts()

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

    inventory = sdtm_inventory([Path(entry["localPath"]) for entry, kind in kinds if kind == "sdtm"])
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
