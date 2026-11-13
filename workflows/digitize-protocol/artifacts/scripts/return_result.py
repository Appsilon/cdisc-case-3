"""Close the digitization run: publish the approved USDM and hand the study package back.

outcome:
  digitized  the gate passed, CORE accepted (every finding fixed or justified)
             and the clinical scientist approved; publishes usdm.json and
             usdm-citations.json exactly as the gate checked them, the review
             page (usdm-view), the CORE files and the review feedback, on top of
             the package the CORE child returned.
  failed     the gate still failed after the last attempt, the CORE child did
             not complete, or CORE still rejected after the last round; the
             agent's files are attached and the package's USDM is unchanged.

Result: { outcome, counts, summary, files, package }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gate import publish_copy  # noqa: E402
from mfpkg import files_of_kind, read_input, replace_files, run_main, step_file, step_output, with_history, write_result  # noqa: E402
from usdmlib import LOOP, USDM_DIR, USDM_FILES, WORKFLOW, base_package  # noqa: E402

CORE_KINDS = ("core-report-usdm", "core-issue-index-usdm", "core-dispositions-usdm")
KINDS = {"usdm.json": "usdm", "usdm-citations.json": "usdm-citations"}


def failed(package: dict, counts: dict, files: list[dict], summary: str) -> None:
    write_result({"outcome": "failed", "counts": counts, "summary": f"FAILED: {summary}", "files": files,
                  "package": with_history(package, WORKFLOW, "failed")})


def main() -> None:
    step_input = read_input()
    gate = step_output(step_input, "check-usdm")
    core = step_output(step_input, "validate-usdm")
    child = core.get("output") or {}
    counts = gate.get("counts") or {}
    package = base_package(step_input)

    if gate.get("needsFix") is True:
        problems = gate.get("problems") or []
        drafts = [entry for entry in (publish_copy(USDM_DIR / name, KINDS[name], WORKFLOW) for name in USDM_FILES) if entry]
        failed(package, counts, drafts, f"the USDM gate still reports {len(problems)} problem(s) after {gate.get('attempt')} attempt(s), first: "
               + (problems[0] if problems else "unknown") + ". The agent's files are attached.")
        return

    checked = [entry for entry in (step_file("check-usdm", name, KINDS[name], WORKFLOW) for name in USDM_FILES) if entry]
    if core.get("status") != "completed":
        failed(package, counts, checked, f"the CORE validation child ended {core.get('status') or 'without a status'}.")
        return
    core_files = files_of_kind(child.get("package") or {}, *CORE_KINDS)
    if child.get("outcome") != "accepted":
        rounds = step_output(step_input, "route-core").get("round")
        failed(package, counts, checked + core_files, f"CORE still rejected the USDM after {rounds} round(s): {child.get('summary')}")
        return

    view = step_file("prepare-review", "usdm-review.html", "usdm-view", WORKFLOW)
    feedback = publish_copy(LOOP.review_feedback_path, f"review-feedback-{WORKFLOW}", WORKFLOW)
    added = [entry for entry in (view, feedback) if entry]
    write_result({
        "outcome": "digitized", "counts": counts,
        "summary": f"DIGITIZED: {counts.get('objectives', 0)} objectives / {counts.get('endpoints', 0)} endpoints, {counts.get('arms', 0)} arms, "
                   f"{counts.get('encounters', 0)} encounters × {counts.get('activities', 0)} activities, {counts.get('citations', 0)} citations; "
                   f"CORE accepted, approved by the clinical scientist.",
        "files": checked + added + core_files,
        "package": with_history(replace_files(child.get("package") or {}, added), WORKFLOW, "digitized"),
    })


if __name__ == "__main__":
    run_main(main)
