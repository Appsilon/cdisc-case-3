"""End-to-end check of the ard-tfl-generation scripts with real R, fixture programs standing in for the agent.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath, one shared /workspace). Fixtures: a 12-subject ADSL/ADAE, a plan
with one table, one figure and one blocked output, and programs that follow
the contract (tests/fixtures/programs).

  1. package mode, clean programs -> executed, every displayed number reconciled, viewer, outcome generated
  2. a number typed into the display, a bad tag, a missing program -> sent back; three attempts -> failed
  3. a cell showing another arm's mean (a value the ARD holds, in the wrong row) -> rejected
  4. upload mode, a review round, then 'spec-change' -> outcome upstream_change with the request
  5. the cell checks on their own: missing / miscounted / out-of-range data-ard, an off-by-one digit
     that equals another ARD stat, bounds (<0.001) and percentages

Needs R with haven, jsonlite and ggplot2:
  python3 tests/test_pipeline.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parent / "artifacts"
SHARED = HERE.parent.parent / "shared"
FIXTURES = HERE / "fixtures"
INPUT_KINDS = {"tlf-plan.json": "tlf-plan", "analysis-spec.json": "analysis-spec", "reporting-event.json": "ars", "lineage.json": "lineage"}


class Run:
    """One simulated workflow run: a worktree (/workspace), its step outputs and variables."""

    def __init__(self, root: Path):
        self.root = root
        self.workspace = root / "workspace"
        self.steps_dir = self.workspace / ".mediforce" / "output"
        self.scripts = root / "artifacts" / "scripts"
        shutil.copytree(ARTIFACTS / "scripts", self.scripts)
        for helper in SHARED.glob("*.py"):
            shutil.copyfile(helper, self.scripts / helper.name)
        self.variables: dict[str, dict] = {}
        self.previous: dict = {}

    def environment(self, step_id: str) -> dict:
        return {**os.environ, "MEDIFORCE_OUTPUT_DIR": str(self.steps_dir / step_id), "MEDIFORCE_STEP_OUTPUTS_DIR": str(self.steps_dir),
                "MEDIFORCE_WORKSPACE_DIR": str(self.workspace), "RUN_ID": f"run-{self.root.name}", "STEP_ID": step_id}

    def step(self, step_id: str, script: str, params: dict | None = None, files: list[dict] | None = None) -> dict:
        output_dir = self.steps_dir / step_id
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True)
        step_input = {**self.previous, "steps": self.variables, **(params or {})}
        if files is not None:
            step_input["files"] = files
        (output_dir / "input.json").write_text(json.dumps(step_input), encoding="utf-8")
        completed = subprocess.run([sys.executable, str(self.scripts / script)], env=self.environment(step_id), capture_output=True, text=True)
        result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
        if completed.returncode != 0:
            raise AssertionError(f"{step_id} failed: {result.get('error')}\n{completed.stderr[-3000:]}")
        self.variables[step_id] = result
        self.previous = result
        return result

    def output(self, step_id: str, result: dict) -> None:
        self.variables[step_id] = result
        self.previous = result

    def agent(self, programs: Path) -> None:
        target = self.workspace / "tlf-programs"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(programs, target)
        self.output("author-programs", {"summary": "fixture programs"})

    def self_check(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.scripts / "self_check.py")], env=self.environment("author-programs"), capture_output=True, text=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(path: Path, kind: str | None) -> dict:
    item = {"name": path.name, "downloadUrl": f"/api/attachments/{path.name}/blob", "sha256": sha(path), "localPath": str(path)}
    return {**item, "kind": kind} if kind else item


def input_files(with_kinds: bool) -> list[dict]:
    files = [entry(path, "adam" if with_kinds else None) for path in sorted((FIXTURES / "adam").glob("*.xpt"))]
    return files + [entry(FIXTURES / name, kind if with_kinds else None) for name, kind in INPUT_KINDS.items()]


def without_local(files: list[dict]) -> list[dict]:
    return [{key: value for key, value in item.items() if key != "localPath"} for item in files]


def with_local(files: list[dict], source: list[dict]) -> list[dict]:
    local = {item["name"]: item["localPath"] for item in source}
    return [{**item, "localPath": local[item["name"]]} for item in files]


def staged_run(root: Path) -> Run:
    run = Run(root)
    files = input_files(with_kinds=True)
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local(files)}})
    assert resolved["needsUpload"] is False and len(resolved["files"]) == 6, resolved
    staged = run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    assert staged["datasets"] == ["ADAE", "ADSL"] and staged["outputs"] == ["F-14-1", "T-14-2.01"], staged
    return run


def test_generated(work: Path) -> None:
    run = staged_run(work / "generated")
    run.agent(FIXTURES / "programs")
    checked = run.self_check()
    assert checked.returncode == 0 and checked.stdout.startswith("PASS"), checked.stdout + checked.stderr
    assert (run.workspace / "ard-tfl-generation" / "attempts.json").is_file() is False, "self-check must not use an attempt"

    executed = run.step("execute-programs", "execute_programs.py")
    assert executed["needsFix"] is False and [item["id"] for item in executed["outputs"]] == ["F-14-1", "T-14-2.01"], executed
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["needsFix"] is False and reconciled["checked"] == 9 and reconciled["unmatched"] == 0, reconciled
    page = (run.steps_dir / "reconcile" / "tlf-viewer.html").read_text()
    for expected in ("AN.T-14-2.01", "adsl.R lines [12, 14]", "data:image/png;base64,", "srcdoc=", "@tlf F-14-1", "stat_name",
                     "title=&quot;ARD #4: group1_level=Drug Low, variable=AGE, context=continuous, stat_name=mean"):
        assert expected in page, expected

    run.output("review-tlfs", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "generated" and result["outputs"] == ["F-14-1", "T-14-2.01"], result
    kinds = {item["name"]: item["kind"] for item in result["package"]["files"]}
    assert kinds["T-14-2.01.json"] == "ard" and kinds["F-14-1.png"] == "tfl" and kinds["tlf-viewer.html"] == "tfl", kinds
    assert kinds["T-14-2.01.R"] == "tfl-program" and kinds["setup.R"] == "tfl-program" and kinds["F-14-1.log"] == "tfl-log", kinds
    assert kinds["adsl.xpt"] == "adam" and kinds["analysis-spec.json"] == "analysis-spec"


def broken_programs(work: Path) -> Path:
    target = work / "broken-programs"
    shutil.copytree(FIXTURES / "programs", target)
    table = target / "T-14-2.01.R"
    table.write_text(table.read_text().replace('fmt(cell(arm, "mean"), 1)', '"99.9"'))
    (target / "F-14-1.R").unlink()
    return target


def test_failures(work: Path) -> None:
    run = staged_run(work / "broken")
    run.agent(broken_programs(work))
    executed = run.step("execute-programs", "execute_programs.py")
    assert executed["needsFix"] is True and executed["retry"] is True, executed
    assert "No program for planned output(s) F-14-1" in "\n".join(executed["problems"]), executed["problems"]

    shutil.copyfile(FIXTURES / "programs" / "F-14-1.R", run.workspace / "tlf-programs" / "F-14-1.R")
    figure = run.workspace / "tlf-programs" / "F-14-1.R"
    figure.write_text(figure.read_text().replace("uses=ADSL.TRT01P", "uses=ADSL.NOPE,ADSL.TRT01P"))
    executed = run.step("execute-programs", "execute_programs.py")
    assert executed["attempt"] == 2 and "uses ADSL.NOPE, which the delivered ADaM does not contain" in "\n".join(executed["problems"])

    shutil.copyfile(FIXTURES / "programs" / "F-14-1.R", figure)
    executed = run.step("execute-programs", "execute_programs.py")
    assert executed["needsFix"] is False, executed
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["needsFix"] is True and reconciled["retry"] is False and reconciled["unmatched"] == 3, reconciled
    assert reconciled["problems"][0].startswith(
        "T-14-2.01: row 'Mean (SD)', column 2: shows 99.9, but ARD row 1 (group1_level=Placebo, variable=AGE, context=continuous, "
        "stat_name=mean) is "), reconciled
    feedback = json.loads((run.workspace / "ard-tfl-generation" / "feedback.json").read_text())
    assert feedback["step"] == "reconcile" and feedback["problems"] == reconciled["problems"]
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "failed" and "ard" not in {item["kind"] for item in result["package"]["files"]}, result


def test_wrong_row(work: Path) -> None:
    run = staged_run(work / "wrong-row")
    target = work / "wrong-row-programs"
    shutil.copytree(FIXTURES / "programs", target)
    table = target / "T-14-2.01.R"
    table.write_text(table.read_text().replace('fmt(cell(arm, "mean"), 1)', 'fmt(cell(arms[match(arm, arms) %% 3 + 1], "mean"), 1)'))
    run.agent(target)
    run.step("execute-programs", "execute_programs.py")
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["needsFix"] is True and reconciled["unmatched"] == 3, reconciled
    assert "row 'Mean (SD)', column 2: shows " in reconciled["problems"][0] and "ARD row 1 (" in reconciled["problems"][0], reconciled


def test_cell_checks(work: Path) -> None:
    sys.path[:0] = [str(ARTIFACTS / "scripts"), str(SHARED)]
    from tfllib import reconcile_output

    ard = [{"variable": "AGE", "stat_name": "mean", "stat": 73.64}, {"variable": "AGE", "stat_name": "mean", "stat": 73.74},
           {"variable": "AE", "stat_name": "p", "stat": 0.29411}, {"variable": "AE", "stat_name": "p.value", "stat": 0.0004},
           {"variable": "AE", "stat_name": "label", "stat": "n (%)"}, {"variable": "AE", "stat_name": "diff", "stat": "-1.5"},
           {"variable": "AE", "stat_name": "diff", "stat": [-2]}, {"variable": "AE", "stat_name": "n", "stat": 1}]
    (work / "cells.json").write_text(json.dumps(ard))

    def problems(cells: str) -> list[str]:
        (work / "cells.html").write_text(f"<table><tr><th></th><th>A</th></tr><tr><td>label</td>{cells}</tr></table>")
        return [item["problem"] for item in reconcile_output("T-1", work / "cells.html", work / "cells.json")["unmatched"]]

    assert problems("<td data-ard='0'>73.6</td><td data-ard='2,3'>29.4 &lt;0.001</td><td>NE</td>") == []
    assert problems("<td data-ard='0'>73.7</td>") == ["shows 73.7, but ARD row 0 (variable=AGE, stat_name=mean) is 73.64"], \
        "an off-by-one digit must fail even though ARD row 1 rounds to it"
    assert problems("<td>73.6</td>") == ["shows '73.6' without data-ard (the 0-based ARD row of each number)"]
    assert problems("<td data-ard='0'>73.6 (29.4)</td>") == ["shows '73.6 (29.4)': 2 number(s) but data-ard='0' names 1 ARD row(s)"]
    assert problems("<td data-ard='9'>1</td>") == ["data-ard index 9 is outside the ARD (rows 0-7)"]
    assert problems("<td data-ard='a'>1</td>") == ["data-ard='a' is not a comma-separated list of 0-based ARD row indices"]
    assert problems("<td data-ard='4'>1</td>") == ["shows 1, but ARD row 4 (variable=AE, stat_name=label) has no single numeric stat"]
    assert problems("<td data-ard='2'>&lt;0.001</td>") == ["shows <0.001, but ARD row 2 (variable=AE, stat_name=p) is 0.29411"]
    assert problems("<td data-ard='2'>&gt;0.999</td>") == ["shows >0.999, but ARD row 2 (variable=AE, stat_name=p) is 0.29411"], \
        "a bound must not pass through the x100 reading"
    assert problems("<td data-ard='3'>p&lt;0.001</td><td data-ard='2,5,6'>29.41% -1.5 −2</td>") == []
    assert problems("<td data-ard='7'>100</td>") == ["shows 100, but ARD row 7 (variable=AE, stat_name=n) is 1"], \
        "a count of 1 is not 100 unless the cell says %"
    assert problems("<td data-ard='7'>100.0%</td>") == []
    assert problems("<td data-ard='7'>100.0</td>") == [], "a proportion of 1 in a % column shows as 100.0"
    assert problems("<td data-ard='²'>1</td>") == ["data-ard='²' is not a comma-separated list of 0-based ARD row indices"]
    (work / "listing.html").write_text("<table><tr><td>01-701-1015</td><td>2014-01-02</td><td data-ard='0'>73.7</td></tr></table>")
    listed = reconcile_output("L-1", work / "listing.html", work / "cells.json", listing=True)["unmatched"]
    assert [item["problem"] for item in listed] == ["shows 73.7, but ARD row 0 (variable=AGE, stat_name=mean) is 73.64"], listed

    from reconcile import linked_display
    linked = linked_display("<html><HEAD></HEAD><table><tr><td>a</td><td data-ard=4>x</td></tr></table></html>",
                            [*ard[:4], {"variable": "AE", "stat_name": "label", "stat": "<\"n\">"}])
    assert "<td data-ard=4 title=\"ARD #4: variable=AE, stat_name=label, stat=&lt;&quot;n&quot;&gt;\">" in linked, linked
    assert "<style>[data-ard]:hover" in linked.split("</HEAD>")[0], linked


def test_upload_review_and_upstream(work: Path) -> None:
    run = Run(work / "upload")
    assert run.step("resolve-inputs", "resolve_inputs.py", {"package": {}})["needsUpload"] is True
    staged = run.step("stage-inputs", "stage_inputs.py", files=input_files(with_kinds=False))
    assert {item["name"]: item["kind"] for item in staged["inputFiles"]} == {
        "adae.xpt": "adam", "adsl.xpt": "adam", **INPUT_KINDS}, staged["inputFiles"]
    run.agent(FIXTURES / "programs")
    run.step("execute-programs", "execute_programs.py")
    run.step("reconcile", "reconcile.py")
    run.output("review-tlfs", {"verdict": "revise", "reviewerComment": "Show the median as well."})
    assert run.step("record-review", "record_review.py")["iteration"] == 1
    assert (run.workspace / "ard-tfl-generation" / "attempts.json").is_file() is False, "a review round gets fresh attempts"
    run.agent(FIXTURES / "programs")
    assert run.step("execute-programs", "execute_programs.py")["attempt"] == 1
    run.step("reconcile", "reconcile.py")
    run.output("review-tlfs", {"verdict": "spec-change", "reviewerComment": "Age needs the ITT population, not safety."})
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "upstream_change" and result["request"] == "Age needs the ITT population, not safety.", result
    assert "ard" not in {item["kind"] for item in result["package"]["files"]}, "an upstream change publishes no ARD into the package"


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for test in (test_generated, test_failures, test_wrong_row, test_upload_review_and_upstream, test_cell_checks):
            test(work)
            print(f"ok  {test.__name__}")


if __name__ == "__main__":
    main()
