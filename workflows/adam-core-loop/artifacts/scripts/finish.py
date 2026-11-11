"""Close an accepted loop: return the validated study package and how it got there.

Result: { outcome: accepted, rounds, summary, files, package }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, step_output, with_history, write_result  # noqa: E402

WORKFLOW = "adam-core-loop"


def main() -> None:
    step_input = read_input()
    validated = step_output(step_input, "validate-adam").get("output") or {}
    package = validated.get("package")
    if isinstance(package, dict) is False or not package.get("files"):
        raise StepFailure("validate-adam returned no study package.")
    rounds = int(step_output(step_input, "route").get("round", 0))
    write_result({
        "outcome": "accepted",
        "rounds": rounds,
        "summary": f"ACCEPTED after {rounds} derivation round(s). {validated.get('summary', '')}".strip(),
        "files": [entry for entry in package["files"] if str(entry.get("kind", "")).startswith("core-")],
        "package": with_history(package, WORKFLOW, "accepted"),
    })


if __name__ == "__main__":
    run_main(main)
