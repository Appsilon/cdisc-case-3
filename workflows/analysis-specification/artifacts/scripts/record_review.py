"""Hand the reviewer's change request back to the spec agent.

Appends the comment of a 'revise' verdict to
/workspace/analysis-specification/review-feedback.jsonl (the agent reads the last line;
the whole file is the raw material for skill learning) and gives the gate a
fresh set of attempts for the revised specs.

Result: { iteration, comment, summary }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, now_iso, read_input, run_main, step_output, write_result  # noqa: E402
from speclib import REVIEW_FEEDBACK_PATH, reset_attempts  # noqa: E402


def main() -> None:
    review = step_output(read_input(), "review-specs")
    comment = str(review.get("reviewerComment") or review.get("comment") or "").strip()
    if not comment:
        raise StepFailure("The specs were sent back without a comment; the spec agent needs to know what to change.")
    previous = REVIEW_FEEDBACK_PATH.read_text(encoding="utf-8").splitlines() if REVIEW_FEEDBACK_PATH.is_file() else []
    iteration = len(previous) + 1
    line = {"skill": "tlf-analysis-spec", "iteration": iteration, "comment": comment, "at": now_iso()}
    with open(REVIEW_FEEDBACK_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")
    reset_attempts()
    write_result({"iteration": iteration, "comment": comment, "summary": f"Revision {iteration} requested: {comment[:200]}"})


if __name__ == "__main__":
    run_main(main)
