"""finish.py groups the final package into deliverables, each file once, with the run that produced it.

  python3 tests/test_finish.py
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


def entry(name: str, kind: str, run: str) -> dict:
    return {"name": name, "kind": kind, "downloadUrl": f"/api/runs/{run}/files/{name}", "sha256": "0", "producedBy": {"runId": run}}


def run_finish(work: Path, step_input: dict) -> tuple[int, dict]:
    scripts = work / "scripts"
    shutil.copytree(SCRIPTS, scripts)
    for helper in SHARED.glob("*.py"):
        shutil.copyfile(helper, scripts / helper.name)
    output = work / "output"
    output.mkdir()
    (output / "input.json").write_text(json.dumps(step_input))
    completed = subprocess.run([sys.executable, str(scripts / "finish.py")], env={**os.environ, "MEDIFORCE_OUTPUT_DIR": str(output), "RUN_ID": "master"},
                               capture_output=True, text=True)
    return completed.returncode, json.loads((output / "result.json").read_text())


def main() -> None:
    files = [entry("tlf-viewer.html", "tfl", "gen"), entry("T-14-2.01.html", "tfl", "gen"), entry("T-14-2.01.json", "ard", "gen"),
             entry("adsl.xpt", "adam", "derive"), entry("core-report.html", "core-report-adamig", "core"), entry("usdm.json", "usdm", "plan")]
    package = {"study": {"id": "CDISCPILOT01"}, "files": files, "history": [{"workflow": "tlf-planning", "runId": "plan", "outcome": "planned"}]}
    with tempfile.TemporaryDirectory() as temporary:
        code, result = run_finish(Path(temporary) / "ok", {"steps": {"generate": {"status": "completed", "output": {"outcome": "generated", "package": package}}}})
        assert code == 0 and result["outcome"] == "complete", result
        titles = [group["title"] for group in result["deliverables"]]
        assert titles[0].startswith("TLF viewer") and [item["name"] for item in result["deliverables"][0]["files"]] == ["tlf-viewer.html"], result
        names = [item["name"] for group in result["deliverables"] for item in group["files"]]
        assert sorted(names) == sorted(item["name"] for item in files), "every file listed exactly once"
        assert result["package"]["history"][-1]["workflow"] == "protocol-to-tfl-modular"
        code, result = run_finish(Path(temporary) / "empty", {"steps": {"generate": {"status": "completed", "output": {}}}})
        assert code != 0 and "no study package" in result["error"], result
    print("ok  test_finish")


if __name__ == "__main__":
    main()
