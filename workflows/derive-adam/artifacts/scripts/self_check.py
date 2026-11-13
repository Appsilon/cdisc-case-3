"""Run the execute-programs and check-lineage gates on /workspace/programs, as the next steps will.

For the agent, before it finishes: the same fresh-session execution and the
same lineage checks, printed as a list of problems, ending in PASS or FAIL.
Uses no attempt and writes no feedback; outputs go to a scratch folder.

Usage: python3 /artifacts/scripts/self_check.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEPT = Path(tempfile.gettempdir()) / "adam-self-check-last"


def run_gate(script: str, scratch: Path) -> dict:
    output_dir = scratch / script.removesuffix(".py").replace("_", "-")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input.json").write_text("{}", encoding="utf-8")
    environment = {**os.environ, "ADAM_SELF_CHECK": "1", "ADAM_RUN_DIR": str(scratch / "run"), "MEDIFORCE_OUTPUT_DIR": str(output_dir), "MEDIFORCE_STEP_OUTPUTS_DIR": str(scratch)}
    completed = subprocess.run([sys.executable, str(HERE / script)], env=environment, capture_output=True, text=True)
    result_path = output_dir / "result.json"
    if result_path.is_file() is False:
        return {"problems": [f"{script} crashed: {completed.stderr.strip()[-1500:]}"]}
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") == "failed":
        return {"problems": [str(result.get("error"))]}
    return result


def main() -> None:
    scratch = Path(tempfile.mkdtemp(prefix="adam-self-check-"))
    try:
        for script in ("execute_programs.py", "check_lineage.py"):
            result = run_gate(script, scratch)
            problems = result.get("problems") or []
            print(f"== {script}: {'FAIL' if problems else 'ok'} — {result.get('summary', '')}")
            for problem in problems:
                print(f"  - {problem}")
            if problems:
                print(f"Logs: {KEPT / 'execute-programs' / 'logs'}")
                print("FAIL")
                sys.exit(1)
        print("PASS")
    finally:
        shutil.rmtree(KEPT, ignore_errors=True)
        shutil.move(str(scratch), KEPT)


if __name__ == "__main__":
    main()
