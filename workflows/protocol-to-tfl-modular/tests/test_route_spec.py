"""route_spec.py: specify after SDTM validation, loop back on a TLF spec-change request, stop after two rounds.

  python3 tests/test_route_spec.py
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
SCRIPTS = HERE.parent / "artifacts" / "scripts"
SHARED = HERE.parent.parent / "shared"
VALIDATED = {"files": [{"name": "dm.xpt", "kind": "sdtm", "downloadUrl": "/a", "sha256": "0"}]}
GENERATED = {"files": [{"name": "analysis-spec.json", "kind": "analysis-spec", "downloadUrl": "/b", "sha256": "0"}]}


def route(work: Path, steps: dict) -> tuple[int, dict]:
    scripts = work / "scripts"
    if scripts.is_dir() is False:
        shutil.copytree(SCRIPTS, scripts)
        for helper in SHARED.glob("*.py"):
            shutil.copyfile(helper, scripts / helper.name)
    output = work / "output"
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir()
    (output / "input.json").write_text(json.dumps({"steps": steps}))
    completed = subprocess.run([sys.executable, str(scripts / "route_spec.py")], env={**os.environ, "MEDIFORCE_OUTPUT_DIR": str(output)},
                               capture_output=True, text=True)
    return completed.returncode, json.loads((output / "result.json").read_text())


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        validated = {"validate-sdtm": {"status": "completed", "output": {"outcome": "accepted", "package": VALIDATED}}}
        code, first = route(work, validated)
        assert code == 0 and first["target"] == "specify" and first["round"] == 0 and first["request"] == "" and first["package"] == VALIDATED, first

        change = {"status": "completed", "output": {"outcome": "upstream_change", "request": "Use ITT for T-14-2.01.", "package": GENERATED}}
        state = first
        for expected_round in (1, 2):
            code, state = route(work, {**validated, "route-spec": state, "generate": change})
            assert code == 0 and state["target"] == "specify" and state["round"] == expected_round, state
            assert state["request"] == "Use ITT for T-14-2.01." and state["package"] == GENERATED, state
        code, state = route(work, {**validated, "route-spec": state, "generate": change})
        assert code == 0 and state["target"] == "exhausted" and state["round"] == 3, state

        silent = {"status": "completed", "output": {"outcome": "upstream_change", "request": " ", "package": GENERATED}}
        code, result = route(work, {**validated, "route-spec": first, "generate": silent})
        assert code == 0 and result["target"] == "exhausted" and "without saying what to change" in result["summary"], result
        code, result = route(work, {"validate-sdtm": {"status": "completed", "output": {}}})
        assert code != 0 and "validate-sdtm returned no study package" in result["error"], result
    print("ok  test_route_spec")


if __name__ == "__main__":
    main()
