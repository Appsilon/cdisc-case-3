"""The agent's own gate run: execute every program and reconcile, as the workflow will, without using an attempt.

  python3 /artifacts/scripts/self_check.py    -> PASS, or the problems to fix
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        environment = {**os.environ, "TFL_SELF_CHECK": "1", "TFL_RUN_DIR": str(Path(scratch) / "run"), "MEDIFORCE_OUTPUT_DIR": scratch}
        (Path(scratch) / "input.json").write_text("{}", encoding="utf-8")
        problems = []
        for script in ("execute_programs.py", "reconcile.py"):
            subprocess.run([sys.executable, str(HERE / script)], env=environment, check=False)
            result = json.loads((Path(scratch) / "result.json").read_text(encoding="utf-8"))
            problems += result.get("problems") or ([result["error"]] if result.get("error") else [])
            if problems:
                break
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
