"""Hand the specification child its package, and loop back when the TLF review asks for a spec change.

Runs after validate-with-core and after every generate-ard-tlfs that ends in upstream_change.
It reads its own previous decision to know which of the two just finished.

  after validate-with-core       -> specify-analyses from the validated package, no request
  after generate-ard-tlfs        -> (spec change) specify-analyses again from its package with the
                                    reviewer's request, while rounds remain,
                                    else exhausted (a human takes over); a request
                                    without a comment also stops for a human

The SDTM does not change in a spec-change round, so the loop goes straight back
to specify -> derive-adam -> generate; CORE SDTMIG validation is not repeated.

Result: { target: specify|exhausted, round, package, request, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, step_output, write_result  # noqa: E402

MAX_CHANGE_ROUNDS = 2


def child_output(step_input: dict, step_id: str) -> dict:
    child = step_output(step_input, step_id)
    output = child.get("output") if isinstance(child.get("output"), dict) else {}
    package = output.get("package")
    if isinstance(package, dict) is False or not package.get("files"):
        raise StepFailure(f"{step_id} returned no study package (status {child.get('status')!r}).")
    return output


def main() -> None:
    step_input = read_input()
    previous = step_output(step_input, "route-spec")

    if previous.get("round") is None:
        output = child_output(step_input, "validate-with-core")
        write_result({"target": "specify-analyses", "round": 0, "package": output["package"], "request": "",
                      "summary": "Specifying the analyses from the validated SDTM and the approved plan."})
        return

    output = child_output(step_input, "generate-ard-tlfs")
    request = str(output.get("request") or "").strip()
    round_number = int(previous["round"]) + 1
    if not request:
        write_result({"target": "exhausted", "round": round_number, "package": output["package"], "request": "",
                      "summary": "The TLF review asked for a spec change without saying what to change; stopping for a human."})
        return
    if round_number > MAX_CHANGE_ROUNDS:
        write_result({"target": "exhausted", "round": round_number, "package": output["package"], "request": request,
                      "summary": f"The TLF review asked for a spec change again after {MAX_CHANGE_ROUNDS} round(s); stopping for a human: {request[:200]}"})
        return
    write_result({"target": "specify-analyses", "round": round_number, "package": output["package"], "request": request,
                  "summary": f"Spec change round {round_number}: {request[:200]}"})


if __name__ == "__main__":
    run_main(main)
