"""After CORE rejected the USDM: count the round and lift the CORE files to the top level for record-core.

The CORE child's files sit inside its result (`output.package`); the runtime
downloads only a step's top-level `files`, so this step hands the JSON report and
the dispositions on as `files` - record-core, which follows, then reads them
locally. After MAX_CORE_ROUNDS rejections in one review round (record-review resets
the count) the run ends as failed instead.

Result: { retry, round, files, summary }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import files_of_kind, read_input, run_main, step_output, write_result  # noqa: E402
from usdmlib import WORK_DIR  # noqa: E402

MAX_CORE_ROUNDS = 3
ROUNDS_PATH = WORK_DIR / "core-rounds.json"  # also cleared by record_review.py


def main() -> None:
    child = step_output(read_input(), "validate-usdm").get("output") or {}
    package = child.get("package") or {}
    rejections = (json.loads(ROUNDS_PATH.read_text(encoding="utf-8")).get("rejections", 0) if ROUNDS_PATH.is_file() else 0) + 1
    ROUNDS_PATH.write_text(json.dumps({"rejections": rejections}), encoding="utf-8")
    retry = rejections < MAX_CORE_ROUNDS
    report = [entry for entry in files_of_kind(package, "core-report-usdm") if entry["name"].endswith(".json")]
    files = report + files_of_kind(package, "core-dispositions-usdm") if retry else []
    write_result({
        "retry": retry, "round": rejections, "files": files,
        "summary": (f"CORE rejected the USDM (round {rejections}/{MAX_CORE_ROUNDS}): the findings marked fix go back to the agent."
                    if retry else f"CORE rejected the USDM {rejections} times: stopping, the run ends as failed."),
    })


if __name__ == "__main__":
    run_main(main)
