"""Walk route.py and finish.py through the loop the way the platform would.

Each call writes input.json (stepParams + `steps` = latest output per step id,
run-workflow outputs shaped {instanceId, status, output}) and reads result.json.

  python3 tests/test_route.py
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


def package(*kinds: str, tag: str = "") -> dict:
    return {"study": {"id": "CDISCPILOT01"}, "files": [{"name": f"{kind}{tag}", "downloadUrl": f"/u/{kind}{tag}", "kind": kind} for kind in kinds]}


def child(output: dict, status: str = "completed") -> dict:
    return {"instanceId": "child", "definitionName": "x", "status": status, "error": None, "output": output}


class Loop:
    def __init__(self, root: Path, params: dict):
        self.root = root
        self.params = params
        self.steps: dict[str, dict] = {}
        self.scripts = root / "scripts"
        shutil.copytree(SCRIPTS, self.scripts)
        for helper in SHARED.glob("*.py"):
            shutil.copyfile(helper, self.scripts / helper.name)

    def run(self, step_id: str, script: str, expect_failure: bool = False) -> dict:
        output_dir = self.root / step_id
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True)
        (output_dir / "input.json").write_text(json.dumps({**self.params, "steps": self.steps}), encoding="utf-8")
        completed = subprocess.run([sys.executable, str(self.scripts / script)], capture_output=True, text=True,
                                   env={**os.environ, "MEDIFORCE_OUTPUT_DIR": str(output_dir), "RUN_ID": "loop", "STEP_ID": step_id})
        result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
        assert (completed.returncode != 0) is expect_failure, (step_id, result, completed.stderr[-800:])
        if expect_failure is False:
            self.steps[step_id] = result
        return result


def test_derive_reject_fix_accept(work: Path) -> None:
    loop = Loop(work / "derive", {"package": package("sdtm", "adam-spec"), "start": "derive"})
    first = loop.run("route", "route.py")
    assert (first["target"], first["round"]) == ("derive", 1) and first["package"]["files"][0]["kind"] == "sdtm"
    loop.steps["derive-adam"] = child({"outcome": "derived", "package": package("sdtm", "adam", tag="-1")})
    second = loop.run("route", "route.py")
    assert (second["target"], second["round"]) == ("validate", 1) and second["package"]["files"][1]["name"] == "adam-1"
    loop.steps["validate-adam"] = child({"outcome": "rejected", "package": package("adam", "core-dispositions-adamig", tag="-r1")})
    third = loop.run("route", "route.py")
    assert (third["target"], third["round"]) == ("derive", 2) and third["package"]["files"][1]["kind"] == "core-dispositions-adamig"
    loop.steps["derive-adam"] = child({"outcome": "derived", "package": package("adam", tag="-2")})
    assert loop.run("route", "route.py")["target"] == "validate"
    loop.steps["validate-adam"] = child({"outcome": "accepted", "summary": "ACCEPTED", "package": package("adam", "core-report-adamig", tag="-ok")})
    finished = loop.run("finish", "finish.py")
    assert finished["outcome"] == "accepted" and finished["rounds"] == 2 and [entry["kind"] for entry in finished["files"]] == ["core-report-adamig"]
    print("  derive -> reject -> fix -> accept:", finished["summary"])


def test_validate_first_then_exhausted(work: Path) -> None:
    loop = Loop(work / "validate", {"package": package("adam", "adam-program", "lineage"), "start": "validate"})
    assert loop.run("route", "route.py")["target"] == "validate"
    for expected_round in (1, 2, 3):
        loop.steps["validate-adam"] = child({"outcome": "rejected", "package": package("adam")})
        decision = loop.run("route", "route.py")
        assert (decision["target"], decision["round"]) == ("derive", expected_round), decision
        loop.steps["derive-adam"] = child({"outcome": "derived", "package": package("adam")})
        assert loop.run("route", "route.py")["target"] == "validate"
    loop.steps["validate-adam"] = child({"outcome": "rejected", "package": package("adam")})
    assert loop.run("route", "route.py")["target"] == "exhausted"
    print("  validate first, rejected three times -> exhausted")


def test_bad_starts(work: Path) -> None:
    Loop(work / "empty", {"package": {}, "start": "derive"}).run("route", "route.py", expect_failure=True)
    Loop(work / "noadam", {"package": package("sdtm"), "start": "validate"}).run("route", "route.py", expect_failure=True)
    print("  empty package / validate without ADaM fail clearly")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        for test in (test_derive_reject_fix_accept, test_validate_first_then_exhausted, test_bad_starts):
            print(test.__name__)
            test(Path(temporary))
    print("all passed")


if __name__ == "__main__":
    main()
