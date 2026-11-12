"""Hand the clinical scientist's change request back to the extraction agent (see gate.GateLoop.record_review).

A review round also starts a fresh count of CORE rejections (route_core.py).

Result: { iteration, comment, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import read_input, run_main, write_result  # noqa: E402
from usdmlib import LOOP, WORK_DIR  # noqa: E402


def main() -> None:
    recorded = LOOP.record_review(read_input(), "review-usdm", "protocol-to-usdm")
    (WORK_DIR / "core-rounds.json").unlink(missing_ok=True)
    write_result(recorded)


if __name__ == "__main__":
    run_main(main)
