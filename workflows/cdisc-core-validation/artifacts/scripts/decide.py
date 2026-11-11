"""Close the validation: outcome from the reviewer's dispositions, files for the parent.

Each review row is one rule x dataset finding with a disposition:
  fix             the data (or the code that produced it) must change;
  justified       the finding stands and is explained (goes to the reviewer's guide);
  false-positive  CORE is wrong here, with the reason.
Any `fix` makes the outcome `rejected`; otherwise `accepted`. With no findings
there is no review and the outcome is `accepted`.

Dispositions are merged with the ones the package carried in, keyed by
rule|dataset, so the next validation of the same study shows them as
"previously" and the final package holds every justification.

Result: { outcome, onReject, standard, version, counts, dispositionCounts, summary, files, package }
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import (  # noqa: E402
    OUTPUT_DIR, STEP_OUTPUTS_DIR, StepFailure, now_iso, published_file, read_input, replace_files, run_main,
    step_file, step_output, with_history, write_result,
)

WORKFLOW = "cdisc-core-validation"
DISPOSITIONS = ("fix", "justified", "false-positive")
DATA_KIND = {"sdtmig": "sdtm", "sendig": "send", "adamig": "adam", "usdm": "usdm"}


def current_rows(step_input: dict, options: list[dict]) -> list[dict]:
    """The review rows for *this* report: a loop leaves the previous pass's rows in the run variables."""
    expected = {option["id"] for option in options}
    rows = step_output(step_input, "review-dispositions").get("rows") or []
    rows = [row for row in rows if row.get("itemId") in expected]
    if expected and {row.get("itemId") for row in rows} != expected:
        raise StepFailure("The review rows do not match the current findings; review the dispositions again.")
    return rows


def previous_dispositions(standard: str) -> dict:
    inputs = STEP_OUTPUTS_DIR / "run-core" / "inputs"
    matches = sorted(inputs.glob(f"core-dispositions-{standard}*.json")) if inputs.is_dir() else []
    return (json.loads(matches[0].read_text(encoding="utf-8")).get("dispositions") or {}) if matches else {}


def main() -> None:
    step_input = read_input()
    resolved = step_output(step_input, "resolve-inputs")
    config = resolved.get("config") or {}
    standard = config.get("standard", "")
    run = step_output(step_input, "run-core")
    report = step_output(step_input, "build-report")
    options = report.get("options") or [] if report.get("needsReview") is True else []
    rows = current_rows(step_input, options)
    by_id = {option["id"]: option for option in options}

    dispositions = previous_dispositions(standard)
    for row in rows:
        values = row.get("values") or {}
        disposition = str(values.get("disposition") or "fix")
        disposition = disposition if disposition in DISPOSITIONS else "fix"
        option = by_id[row["itemId"]]
        dispositions[row["itemId"]] = {
            "rule": option["rule"],
            "dataset": option["dataset"],
            "issues": option["issues"],
            "disposition": disposition,
            "justification": str(values.get("justification") or "").strip(),
            "runId": os.environ.get("RUN_ID", ""),
            "at": now_iso(),
        }
    decided = Counter(dispositions[row["itemId"]]["disposition"] for row in rows)
    unexplained = [row["itemId"] for row in rows
                   if dispositions[row["itemId"]]["disposition"] != "fix" and dispositions[row["itemId"]]["justification"] == ""]
    outcome = "rejected" if decided.get("fix", 0) > 0 else "accepted"

    dispositions_path = OUTPUT_DIR / f"core-dispositions-{standard}.json"
    dispositions_path.write_text(json.dumps({"standard": standard, "version": config.get("version"), "dispositions": dispositions}, indent=2), encoding="utf-8")

    report_kind = f"core-report-{standard}"
    candidates = [
        step_file("build-report", "core-report.html", report_kind, WORKFLOW),
        step_file("run-core", "core-report.json", report_kind, WORKFLOW),
        step_file("run-core", "core-report.xlsx", report_kind, WORKFLOW),
        step_file("run-core", "core-report-local.xlsx", report_kind, WORKFLOW),
        step_file("build-report", f"core-issue-index-{standard}.json", f"core-issue-index-{standard}", WORKFLOW),
    ]
    files = [entry for entry in candidates if entry is not None]
    files.append(published_file(dispositions_path, f"core-dispositions-{standard}", WORKFLOW))

    package = resolved.get("package") or {}
    if resolved.get("needsUpload") is True:
        data_kind = DATA_KIND[standard]
        uploaded = []
        for item in run.get("inputFiles") or []:
            kind = "usdm" if item["role"] == "usdm" else (f"{data_kind}-define" if item["role"] == "define" else data_kind)
            uploaded.append({"name": item["name"], "downloadUrl": item["downloadUrl"], "kind": kind, "sha256": item["sha256"],
                             "producedBy": {"workflow": WORKFLOW, "runId": os.environ.get("RUN_ID", ""), "step": "upload-datasets"}})
        package = replace_files(package, uploaded)
    package = with_history(replace_files(package, files), WORKFLOW, outcome)

    counts = report.get("counts") or {}
    detail = ", ".join(f"{count} {name}" for name, count in decided.items()) or "no findings to review"
    warning = f" {len(unexplained)} finding(s) accepted without a justification." if unexplained else ""
    write_result({
        "outcome": outcome,
        "onReject": config.get("onReject", "return"),
        "standard": standard,
        "version": config.get("version"),
        "counts": counts,
        "dispositionCounts": dict(decided),
        "unexplained": unexplained,
        "summary": f"{outcome.upper()}: {standard} {config.get('version')} — {counts.get('issues', 0)} issue(s); dispositions: {detail}.{warning}",
        "files": files,
        "package": package,
    })


if __name__ == "__main__":
    run_main(main)
