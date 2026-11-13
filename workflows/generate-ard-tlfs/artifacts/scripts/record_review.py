"""Hand the reviewer's change request back to the agent (see gate.GateLoop.record_review).

Result: { iteration, comment, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import read_input, run_main, write_result  # noqa: E402
from tfllib import LOOP  # noqa: E402


def main() -> None:
    write_result(LOOP.record_review(read_input(), "review-tlfs", "tlf-generator"))


if __name__ == "__main__":
    run_main(main)
