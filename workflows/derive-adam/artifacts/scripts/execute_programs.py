"""Execute the agent's ADaM programs: the deterministic half of the derivation.

The agent writes code; this step runs it. Each program runs in its own fresh
`Rscript --vanilla` session, in @depends order (ADSL first), against the staged
SDTM only - nothing from the agent's session carries over. A program passes
when it exits cleanly, its log has no ERROR or WARNING line, and the data frame
it saved exports to SAS V5 with a label on every column.

Writes to /output: adam/<dataset>.xpt, logs/<dataset>.log, programs/ (a copy
of exactly the code that ran), manifest.json (columns per dataset).
On a failure the problems go to feedback.json and the run returns to the agent
while attempts remain.

Result: { needsFix, retry, attempt, problems, datasets: [{dataset, rows, columns}], summary }
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adamlib import (  # noqa: E402
    MAX_ATTEMPTS, PROGRAMS_DIR, RUN_DIR, SDTM_COLUMNS_PATH, SDTM_DIR, count_attempt, dataset_programs, depends_on, execution_order, gate,
)
from mfpkg import OUTPUT_DIR, run_main, write_result  # noqa: E402

RUNNER = Path(__file__).resolve().parent / "run_program.R"
RDS_DIR = RUN_DIR / "rds"
PROGRAM_TIMEOUT_SECONDS = int(os.environ.get("ADAM_PROGRAM_TIMEOUT_SECONDS", "900"))
LOG_TAIL_LINES = 15


def sdtm_inventory() -> list[str]:
    """Column names of every staged SDTM dataset, for check-lineage to resolve `src=` against."""
    script = (
        "files <- list.files(Sys.getenv('SDTM_DIR'), full.names = TRUE);"
        "read <- function(path) if (grepl('[.]xpt$', path, ignore.case = TRUE)) haven::read_xpt(path, n_max = 0) else haven::read_sas(path, n_max = 0);"
        "inventory <- setNames(lapply(files, function(path) names(read(path))), toupper(tools::file_path_sans_ext(basename(files))));"
        "jsonlite::write_json(inventory, Sys.getenv('INVENTORY_PATH'))"
    )
    environment = {**os.environ, "SDTM_DIR": str(SDTM_DIR), "INVENTORY_PATH": str(SDTM_COLUMNS_PATH)}
    completed = subprocess.run(["Rscript", "--vanilla", "-e", script], env=environment, capture_output=True, text=True)
    if completed.returncode != 0:
        return ["Could not read the staged SDTM: " + (completed.stderr.strip().splitlines() or ["unknown error"])[-1]]
    return []


def log_problems(dataset: str, log_text: str) -> list[str]:
    flagged = [line for line in log_text.splitlines() if line.startswith(("ERROR: ", "WARNING: "))]
    return [f"{dataset.lower()}.R: {line}" for line in flagged]


def run_program(dataset: str, program: Path, xpt_dir: Path, logs_dir: Path, manifests_dir: Path) -> tuple[dict | None, list[str]]:
    manifest_path = manifests_dir / f"{dataset.lower()}.json"
    environment = {**os.environ, "SDTM_DIR": str(SDTM_DIR), "ADAM_DIR": str(RDS_DIR)}
    command = ["Rscript", "--vanilla", str(RUNNER), str(program), dataset, str(xpt_dir), str(manifest_path)]
    try:
        completed = subprocess.run(command, cwd=PROGRAMS_DIR, env=environment, capture_output=True, text=True, timeout=PROGRAM_TIMEOUT_SECONDS)
        log_text = completed.stdout + completed.stderr
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as timeout:
        log_text = f"{timeout.stdout or ''}{timeout.stderr or ''}\nERROR: timed out after {PROGRAM_TIMEOUT_SECONDS} s"
        exit_code = -1
    (logs_dir / f"{dataset.lower()}.log").write_text(log_text, encoding="utf-8")
    problems = log_problems(dataset, log_text)
    if exit_code != 0 and not problems:
        tail = "\n".join(log_text.splitlines()[-LOG_TAIL_LINES:])
        problems.append(f"{dataset.lower()}.R exited with status {exit_code}:\n{tail}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None
    return (manifest if not problems else None), problems


def main() -> None:
    attempt = count_attempt()
    programs = dataset_programs()
    xpt_dir, logs_dir, manifests_dir = OUTPUT_DIR / "adam", OUTPUT_DIR / "logs", RUN_DIR / "manifests"
    for folder in (xpt_dir, logs_dir, manifests_dir, RDS_DIR):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    if PROGRAMS_DIR.is_dir():
        shutil.copytree(PROGRAMS_DIR, OUTPUT_DIR / "programs", dirs_exist_ok=True)

    problems: list[str] = sdtm_inventory()
    manifests: list[dict] = []
    if not programs:
        problems.append(f"No programs in {PROGRAMS_DIR}: write one <dataset>.R per ADaM dataset.")
        order: list[str] = []
    else:
        try:
            order = execution_order(programs)
        except ValueError as error:
            problems.append(str(error))
            order = []

    failed: set[str] = set()
    for dataset in order:
        blocked = [dep for dep in depends_on(programs[dataset]) if dep in failed]
        if blocked:
            failed.add(dataset)
            problems.append(f"{dataset.lower()}.R not run: it depends on {', '.join(blocked)}, which failed.")
            continue
        manifest, program_problems = run_program(dataset, programs[dataset], xpt_dir, logs_dir, manifests_dir)
        if program_problems:
            failed.add(dataset)
            problems.extend(program_problems)
        else:
            manifests.append(manifest)

    (OUTPUT_DIR / "manifest.json").write_text(json.dumps({"datasets": manifests}, indent=2), encoding="utf-8")
    routing = gate("execute-programs", problems)
    datasets = [{"dataset": item["dataset"], "rows": item["rows"], "columns": len(item["columns"])} for item in manifests]
    if problems:
        summary = (f"Attempt {attempt}/{MAX_ATTEMPTS}: {len(failed)} of {len(order)} program(s) failed"
                   f" ({len(problems)} problem(s)). " + ("Back to the agent." if routing["retry"] else "No attempts left."))
    else:
        summary = f"Attempt {attempt}/{MAX_ATTEMPTS}: {len(order)} program(s) ran with clean logs: " + ", ".join(
            f"{item['dataset']} ({item['rows']} rows)" for item in datasets) + "."
    write_result({**routing, "order": order, "datasets": datasets, "summary": summary})


if __name__ == "__main__":
    run_main(main)
