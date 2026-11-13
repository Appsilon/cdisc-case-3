"""collect_deliverables.py lifts the files to show; finish.py copies them into /output and groups the package into a manifest.

  python3 tests/test_finish.py
"""

from __future__ import annotations

import json
import hashlib
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


def run_script(script: str, work: Path, step_input: dict) -> tuple[int, dict, Path]:
    scripts = work / "scripts"
    shutil.copytree(SCRIPTS, scripts)
    for helper in SHARED.glob("*.py"):
        shutil.copyfile(helper, scripts / helper.name)
    output = work / "output"
    output.mkdir()
    (output / "input.json").write_text(json.dumps(step_input))
    completed = subprocess.run([sys.executable, str(scripts / script)], env={**os.environ, "MEDIFORCE_OUTPUT_DIR": str(output), "RUN_ID": "master"},
                               capture_output=True, text=True)
    return completed.returncode, json.loads((output / "result.json").read_text()), output


def downloaded(files: list[dict], data: Path) -> list[dict]:
    """What the runtime does with top-level files: download each, add localPath (here: write content, record its sha256)."""
    local = []
    for index, item in enumerate(files):
        path = data / str(index) / item["name"]
        path.parent.mkdir(parents=True)
        path.write_text(f"{item['kind']} {item['name']}")
        local.append({**item, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "localPath": str(path)})
    return local


def main() -> None:
    files = [entry("tlf-viewer.html", "tfl", "gen"), entry("T-14-2.01.html", "tfl", "gen"), entry("T-14-2.01.json", "ard", "gen"),
             entry("adsl.xpt", "adam", "derive"), entry("core-report.html", "core-report-adamig", "core"),
             entry("core-report.html", "core-report-sdtmig", "core-sdtm"), entry("usdm.json", "usdm", "plan"),
             entry("usdm-citations.json", "usdm-citations", "digitize")]
    package = {"study": {"id": "CDISCPILOT01"}, "files": files, "history": [{"workflow": "plan-tlfs", "runId": "plan", "outcome": "planned"}]}
    generated = {"steps": {"generate": {"status": "completed", "output": {"outcome": "generated", "package": package}}}}
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        code, collected, _ = run_script("collect_deliverables.py", work / "collect", generated)
        assert code == 0, collected
        assert [item["showAs"] for item in collected["files"]] == ["tlf-viewer.html", "core-report-sdtmig.html", "core-report-adamig.html"], collected
        assert all(item["downloadUrl"] for item in collected["files"]) and collected["package"] == package
        code, result, _ = run_script("collect_deliverables.py", work / "collect-empty", {"steps": {"generate": {"status": "completed", "output": {}}}})
        assert code != 0 and "no study package" in result["error"], result

        finish_input = {**generated, "package": collected["package"], "files": downloaded(collected["files"], work / "data")}
        code, result, output = run_script("finish.py", work / "ok", finish_input)
        assert code == 0 and result["outcome"] == "complete", result
        assert result["shown"] == ["tlf-viewer.html", "core-report-sdtmig.html", "core-report-adamig.html"], result
        assert (output / "core-report-sdtmig.html").read_text() == "core-report-sdtmig core-report.html", "each standard's report under its own name"
        assert (output / "manifest.json").is_file()
        titles = [group["title"] for group in result["deliverables"]]
        assert titles[0].startswith("TLF viewer") and [item["name"] for item in result["deliverables"][0]["files"]] == ["tlf-viewer.html"], result
        names = [item["name"] for group in result["deliverables"] for item in group["files"]]
        assert sorted(names) == sorted(item["name"] for item in files), "every file listed exactly once"
        assert result["package"]["history"][-1]["workflow"] == "protocol-to-tlfs"
        tampered = [{**item, "sha256": "0" * 64} if index == 0 else item for index, item in enumerate(finish_input["files"])]
        code, result, _ = run_script("finish.py", work / "tampered", {**finish_input, "files": tampered})
        assert code != 0 and "sha256 mismatch" in result["error"], result
        code, result, _ = run_script("finish.py", work / "empty", {"steps": {}})
        assert code != 0 and "no study package" in result["error"], result
    print("ok  test_finish")


if __name__ == "__main__":
    main()
