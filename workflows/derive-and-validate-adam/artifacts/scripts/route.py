"""Decide the next move of the ADaM <-> CORE loop and hand on the current study package.

Runs at the start and after every child: derive-adam and validate-with-core each
return to `route`, which reads its own previous decision to know which child
just finished.

  start                    -> `start` input: derive (default) or validate (bring
                              existing ADaM + programs, derive only on reject)
  after derive-adam        -> validate the derived package
  after validate-with-core      -> rejected: derive again (a fix loop: the package now
                              carries the findings marked 'fix') while rounds remain,
                              else exhausted

Result: { target: derive|validate|exhausted, round, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, files_of_kind, read_input, run_main, step_output, write_result  # noqa: E402

MAX_ROUNDS = 3
STARTS = ("derive", "validate")


def child_package(steps_output: dict, step_id: str) -> dict:
    child = steps_output if steps_output else {}
    package = (child.get("output") or {}).get("package")
    if isinstance(package, dict) is False or not package.get("files"):
        raise StepFailure(f"{step_id} returned no study package (status {child.get('status')!r}).")
    return package


def main() -> None:
    step_input = read_input()
    previous = step_output(step_input, "route")
    last_target = previous.get("target")

    if last_target is None:
        package = step_input.get("package")
        if isinstance(package, dict) is False or not package.get("files"):
            raise StepFailure("Start the loop with a study package (kinds sdtm + adam-spec, or adam + adam-program to validate first).")
        start = str(step_input.get("start") or "derive")
        if start not in STARTS:
            raise StepFailure(f"start must be one of {', '.join(STARTS)}, got '{start}'")
        if start == "validate" and not files_of_kind(package, "adam"):
            raise StepFailure("start=validate needs ADaM datasets (kind adam) in the package.")
        target, round_number = start, (1 if start == "derive" else 0)
        summary = f"Starting with {'derivation' if start == 'derive' else 'validation of the supplied ADaM'}."
    elif last_target == "derive":
        package = child_package(step_output(step_input, "derive-adam"), "derive-adam")
        target, round_number = "validate", int(previous.get("round", 1))
        summary = f"Round {round_number}: validating the derived ADaM against ADaMIG."
    elif last_target == "validate":
        package = child_package(step_output(step_input, "validate-with-core"), "validate-with-core")
        round_number = int(previous.get("round", 0)) + 1
        target = "derive" if round_number <= MAX_ROUNDS else "exhausted"
        summary = (f"Round {round_number}: CORE rejected the delivery; fixing the programs behind the findings marked 'fix'."
                   if target == "derive" else f"CORE still rejects after {MAX_ROUNDS} derivation round(s); stopping for a human.")
    else:
        raise StepFailure(f"Unexpected previous route target '{last_target}'.")

    write_result({"target": target, "round": round_number, "package": package, "summary": summary})


if __name__ == "__main__":
    run_main(main)
