"""Execute the agent's TLF programs: the deterministic half of the generation.

The agent writes code; this step runs it. Each program runs in its own fresh
`Rscript --vanilla` session against the staged ADaM only. A program passes
when its @tlf tag resolves (planned output, ARS analysis, ADaM variables that
exist), it exits cleanly, and it wrote a well-formed ARD and its display
(HTML table, or PNG for a figure). Warnings are kept in the log and counted,
not fatal: statistics legitimately warn (sparse cells, approximations).

Writes to /output: ard/<id>.json, tfl/<id>.html|png, logs/<id>.log, programs/
(exactly the code that ran). On a failure the problems go to feedback.json and
the run returns to the agent while attempts remain.

Result: { needsFix, retry, attempt, problems, outputs: [{id, ard, display, warnings}], summary }
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, run_main, write_result  # noqa: E402
from gate import MAX_ATTEMPTS  # noqa: E402
from tfllib import (  # noqa: E402
    ADAM_COLUMNS_PATH, ADAM_DIR, LOOP, PROGRAMS_DIR, RUN_DIR, SELF_CHECK, ard_problems, ars_analysis_ids, planned_outputs, program_problems,
    read_json,
)

PROGRAM_TIMEOUT_SECONDS = int(os.environ.get("TFL_PROGRAM_TIMEOUT_SECONDS", "600"))
LOG_TAIL_LINES = 15


def run_program(final_id: str, output_type: str, ard_dir: Path, tfl_dir: Path, logs_dir: Path) -> tuple[dict, list[str]]:
    environment = {**os.environ, "ADAM_DIR": str(ADAM_DIR), "ARD_DIR": str(ard_dir), "TFL_DIR": str(tfl_dir), "PROGRAMS_DIR": str(PROGRAMS_DIR)}
    try:
        completed = subprocess.run(["Rscript", "--vanilla", f"{final_id}.R"], cwd=PROGRAMS_DIR, env=environment,
                                   capture_output=True, text=True, timeout=PROGRAM_TIMEOUT_SECONDS)
        log_text, exit_code = completed.stdout + completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as timeout:
        log_text, exit_code = f"{timeout.stdout or ''}{timeout.stderr or ''}\nError: timed out after {PROGRAM_TIMEOUT_SECONDS} s", -1
    (logs_dir / f"{final_id}.log").write_text(log_text, encoding="utf-8")
    warnings = sum(1 for line in log_text.splitlines() if line.lstrip().startswith(("Warning", "In addition: Warning")))
    if exit_code != 0:
        tail = "\n".join(log_text.splitlines()[-LOG_TAIL_LINES:])
        return {"id": final_id, "warnings": warnings}, [f"{final_id}.R exited with status {exit_code}:\n{tail}"]
    problems = ard_problems(final_id, ard_dir / f"{final_id}.json")
    html, png = tfl_dir / f"{final_id}.html", tfl_dir / f"{final_id}.png"
    if output_type == "Figure" and png.is_file() is False:
        problems.append(f"{final_id}: a figure writes $TFL_DIR/{final_id}.png")
    if output_type != "Figure" and html.is_file() is False:
        problems.append(f"{final_id}: a {str(output_type).lower()} writes its display as an HTML table to $TFL_DIR/{final_id}.html")
    display = [path.name for path in (html, png) if path.is_file()]
    return {"id": final_id, "ard": f"{final_id}.json", "display": display, "warnings": warnings}, problems


def main() -> None:
    attempt = LOOP.count()
    outputs = planned_outputs()
    adam_columns = read_json(ADAM_COLUMNS_PATH)
    problems, tags = program_problems(outputs, adam_columns, ars_analysis_ids())

    shutil.rmtree(RUN_DIR, ignore_errors=True)
    ard_dir, tfl_dir, logs_dir = RUN_DIR / "ard", RUN_DIR / "tfl", RUN_DIR / "logs"
    for folder in (ard_dir, tfl_dir, logs_dir):
        folder.mkdir(parents=True)
    results = []
    for final_id in sorted(tags):
        result, run_problems = run_program(final_id, str(outputs[final_id]["type"]), ard_dir, tfl_dir, logs_dir)
        results.append(result)
        problems += run_problems

    if SELF_CHECK is False:
        for folder in ("ard", "tfl", "logs"):
            shutil.copytree(RUN_DIR / folder, OUTPUT_DIR / folder, dirs_exist_ok=True)
        if PROGRAMS_DIR.is_dir():
            shutil.copytree(PROGRAMS_DIR, OUTPUT_DIR / "programs", dirs_exist_ok=True)
        (OUTPUT_DIR / "tags.json").write_text(json.dumps(tags, indent=2), encoding="utf-8")
    routing = LOOP.route("execute-programs", problems)
    warnings = sum(item.get("warnings", 0) for item in results)
    summary = (f"Attempt {attempt}/{MAX_ATTEMPTS}: " + (f"{len(problems)} problem(s), first: {problems[0]}" if problems else
               f"{len(results)} program(s) ran and wrote ARD + display" + (f" ({warnings} R warning(s) in the logs)." if warnings else ".")))
    write_result({**routing, "outputs": results, "summary": summary})


if __name__ == "__main__":
    run_main(main)
