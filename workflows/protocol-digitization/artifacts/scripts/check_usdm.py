"""Deterministic gate over the extracted USDM.

Runs the usdmlib checks (USDM 4.0 schema, ids and references, the v1 entities,
citations). On failure the problems go to feedback.json and the work returns to
the agent while attempts remain (three per round; a review or CORE request starts a new round). On pass it publishes
usdm.json + usdm-citations.json and the package the CORE validation child reads (with the previous CORE round's dispositions
and issue index, so the next round pre-fills decisions and reports what is new and fixed).

Result: { needsFix, retry, attempt, problems, counts, summary, package }
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gate import MAX_ATTEMPTS  # noqa: E402
from mfpkg import OUTPUT_DIR, files_of_kind, published_file, read_input, replace_files, run_main, step_output, write_result  # noqa: E402
from usdmlib import CHECK_PATH, CITATIONS, LOOP, USDM, USDM_DIR, USDM_FILES, WORKFLOW, base_package, check_usdm  # noqa: E402

def main() -> None:
    step_input = read_input()
    attempt = LOOP.count()
    result = check_usdm()
    problems = result["problems"]
    CHECK_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    routing = LOOP.route("check-usdm", problems)
    counts = result["counts"]
    if problems:
        write_result({**routing, "counts": counts, "package": {},
                      "summary": f"USDM gate FAILED (attempt {attempt}/{MAX_ATTEMPTS}): {len(problems)} problem(s), first: {problems[0]}"})
        return

    for name in USDM_FILES:
        shutil.copyfile(USDM_DIR / name, OUTPUT_DIR / name)

    checked = [published_file(OUTPUT_DIR / USDM, "usdm", WORKFLOW), published_file(OUTPUT_DIR / CITATIONS, "usdm-citations", WORKFLOW)]
    previous_core = (step_output(step_input, "validate-usdm").get("output") or {}).get("package") or {}
    package = replace_files(base_package(step_input), checked + files_of_kind(previous_core, "core-dispositions-usdm", "core-issue-index-usdm"))
    write_result({
        **routing, "counts": counts, "package": package,
        "summary": f"USDM gate passed: {counts['objectives']} objectives / {counts['endpoints']} endpoints, {counts['arms']} arms, "
                   f"{counts['epochs']} epochs, {counts['inclusion']}+{counts['exclusion']} criteria, {counts['encounters']} encounters × "
                   f"{counts['activities']} activities; {counts['citations']} citations verified on {counts['citedPages']} pages.",
    })


if __name__ == "__main__":
    run_main(main)
