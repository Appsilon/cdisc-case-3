"""Pick where the study starts: digitize the protocol when the package has one but no USDM, else plan.

Runs first, and again after digitize - it reads digitize's result to know which.

  package with a usdm                 -> plan
  package with a protocol, no usdm    -> digitize (protocol-digitization)
  empty package / neither             -> plan (the statistician uploads in the planning run)
  after digitize                      -> plan, with the package digitize returned (now with the USDM)

Result: { target: plan|digitize, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, files_of_kind, read_input, run_main, step_output, write_result  # noqa: E402


def main() -> None:
    step_input = read_input()
    digitized = step_output(step_input, "digitize")
    if digitized:
        package = (digitized.get("output") or {}).get("package")
        if isinstance(package, dict) is False or not files_of_kind(package, "usdm"):
            raise StepFailure(f"protocol-digitization returned no USDM (status {digitized.get('status')!r}).")
        write_result({"target": "plan", "package": package, "summary": "Planning from the USDM digitized from the protocol."})
        return

    package = step_input.get("package")
    package = package if isinstance(package, dict) else {}
    if files_of_kind(package, "usdm"):
        write_result({"target": "plan", "package": package, "summary": "The package has a USDM: planning from it."})
    elif files_of_kind(package, "protocol"):
        write_result({"target": "digitize", "package": package,
                      "summary": "The package has a protocol but no USDM: digitizing the protocol first."})
    else:
        write_result({"target": "plan", "package": package,
                      "summary": "No USDM or protocol in the package: the statistician uploads the inputs in the planning run."})


if __name__ == "__main__":
    run_main(main)
