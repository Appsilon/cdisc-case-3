"""What a delivered SDTM holds, for feasibility and spec checks.

Per domain: record count, variables, and the distinct category / test /
parameter / decoded-term codes (--CAT, --SCAT, --TESTCD, --TEST, --PARMCD,
--PARM, --DECOD), read with R haven - every workflow image carries R, not every
one carries a Python SAS reader. A domain name alone says little: QS may be
split into QSPH + QSSL by instrument.

    sdtm_inventory([Path("qsph.xpt"), ...]) -> {"QSPH": {"records", "variables", "codes": {"QSCAT": {"count", "values"}}}}

An unreadable file becomes {"error": message} instead of failing the step.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from mfpkg import StepFailure

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
