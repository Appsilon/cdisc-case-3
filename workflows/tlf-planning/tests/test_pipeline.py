"""End-to-end check of the tlf-planning scripts, with fixture files standing in for the agents.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath, one shared /workspace). The planner's output is the CDISCPILOT01 plan
from the original UC3 run (tests/fixtures/plan).

  1. package mode, clean plan       -> gate passes, html rendered, outcome planned, package kinds
  2. broken plan (orphan, bad trace, duplicate id, dropped endpoint) -> gate sends it back, then failed
  3. upload mode + a review round   -> files classified, comment recorded, attempts reset

Needs R with haven and jsonlite (the SDTM inventory):
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
        """A non-script step (agent or human): record its output."""
        self.variables[step_id] = result
        self.previous = result

    def planner(self, plan_dir: Path) -> None:
        target = self.workspace / "tlf-planning" / "plan"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(plan_dir, target, ignore=shutil.ignore_patterns("coverage-report.md"))
        self.output("plan-tlfs", {"summary": "fixture plan"})

    def critic(self) -> None:
        audit = self.workspace / "tlf-planning" / "audit"
        audit.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURES / "plan" / "coverage-report.md", audit / "coverage-report.md")
        self.output("audit-plan", {"verdict": "clean-with-caveats", "summary": "fixture audit"})

    def self_check(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.scripts / "self_check.py")], env=self.environment("plan-tlfs"), capture_output=True, text=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(path: Path, kind: str | None) -> dict:
    item = {"name": path.name, "downloadUrl": f"/api/attachments/{path.name}/blob", "sha256": sha(path), "localPath": str(path)}
    return {**item, "kind": kind} if kind else item


def without_local(files: list[dict]) -> list[dict]:
    return [{key: value for key, value in item.items() if key != "localPath"} for item in files]


def with_local(files: list[dict], source: list[dict]) -> list[dict]:
    local = {item["name"]: item["localPath"] for item in source}
    return [{**item, "localPath": local[item["name"]]} for item in files]


def test_planned(work: Path) -> None:
    run = Run(work / "planned")
    files = [entry(FIXTURES / "usdm.json", "usdm"), entry(FIXTURES / "cdiscpilot01-sap.txt", "sap")]
    files += [entry(path, "sdtm") for path in sorted((FIXTURES / "sdtm").glob("*.xpt"))]
    package = {"study": {"id": "CDISCPILOT01"}, "files": without_local(files)}
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": package})
    assert resolved["needsUpload"] is False and {item["kind"] for item in resolved["files"]} == {"usdm", "sap", "sdtm"}, resolved
    staged = run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    inputs = run.workspace / "tlf-planning" / "inputs"
    assert (inputs / "usdm.json").is_file() and (inputs / "sap" / "cdiscpilot01-sap.txt").is_file(), staged
    assert staged["sdtmDomains"] == ["DM", "QSPH"], staged
    inventory = json.loads((inputs / "sdtm-inventory.json").read_text())["domains"]
    assert inventory["QSPH"]["records"] == 2 and inventory["QSPH"]["codes"]["QSCAT"]["values"] == ["PHQ-9"], inventory
    assert inventory["QSPH"]["codes"]["QSTESTCD"] == {"count": 2, "values": ["PHQ0101", "PHQ0102"]}, inventory

    run.planner(FIXTURES / "plan")
    checked = run.self_check()
    assert checked.returncode == 0 and checked.stdout.startswith("PASS"), checked.stdout
    assert (run.workspace / "tlf-planning" / "attempts.json").is_file() is False, "self-check must not use an attempt"
    gate = run.step("check-plan", "check_plan.py")
    assert gate["needsFix"] is False and gate["counts"]["tables"] == 28, gate
    assert gate["counts"]["blockedEndpoints"] == ["Endpoint_1", "Endpoint_2", "Endpoint_6", "Endpoint_7", "Endpoint_8"], gate
    page = (run.steps_dir / "check-plan" / "tlf-plan.html").read_text()
    assert "T-14-1.01" in page and "Flagged" in page and "<script" not in page

    run.critic()
    run.output("review-plan", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "planned" and result["verdict"] == "clean-with-caveats", result
    kinds = sorted({item["kind"] for item in result["package"]["files"]})
    assert kinds == ["coverage-report", "sap", "sdtm", "study-model", "tlf-plan", "usdm"], kinds
    names = {item["name"] for item in result["files"]}
    assert {"study-model.json", "tlf-plan.json", "tlf-index.md", "tlf-plan.html", "coverage-report.md"} <= names, names
    assert all(item["downloadUrl"].startswith("/api/runs/run-planned/files/.mediforce/output/return-result/") for item in result["files"])
    assert result["package"]["history"][-1]["outcome"] == "planned"


def broken_plan(work: Path) -> Path:
    target = work / "broken-plan"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(FIXTURES / "plan", target)
    plan = json.loads((target / "tlf-plan.json").read_text())
    plan[0]["traces_to"] = {"objective_ids": [], "endpoint_ids": [], "regulatory_rule": None}
    plan[1]["traces_to"]["endpoint_ids"] = ["Endpoint_99"]
    plan[2]["candidate_id"] = plan[3]["candidate_id"]
    plan = [item for item in plan if "Endpoint_3" not in (item["traces_to"].get("endpoint_ids") or [])]
    (target / "tlf-plan.json").write_text(json.dumps(plan))
    return target


def test_gate_failure(work: Path) -> None:
    run = Run(work / "broken")
    files = [entry(FIXTURES / "usdm.json", "usdm")]
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local(files)}})
    run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    run.planner(broken_plan(work))
    problems = None
    for attempt in (1, 2, 3):
        gate = run.step("check-plan", "check_plan.py")
        assert gate["needsFix"] is True and gate["attempt"] == attempt and gate["retry"] is (attempt < 3), gate
        problems = gate["problems"]
        feedback = json.loads((run.workspace / "tlf-planning" / "feedback.json").read_text())
        assert feedback["problems"] == problems
    text = "\n".join(problems)
    for expected in ("orphan", "Endpoint_99", "is used 2 times", "Endpoint_3"):
        assert expected in text, (expected, text)
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "failed" and "tlf-plan.json" in {item["name"] for item in result["files"]}, result
    assert "tlf-plan" not in {item["kind"] for item in result["package"]["files"]}, "a failed plan must not enter the package"


def test_upload_and_review(work: Path) -> None:
    run = Run(work / "upload")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {}})
    assert resolved["needsUpload"] is True
    sdtm = work / "dm.xpt"
    sdtm.write_bytes(b"not really xpt")
    uploads = [entry(FIXTURES / "usdm.json", None), entry(FIXTURES / "cdiscpilot01-sap.txt", None), entry(sdtm, None)]
    staged = run.step("stage-inputs", "stage_inputs.py", files=uploads)
    assert {item["name"]: item["kind"] for item in staged["inputFiles"]} == {"usdm.json": "usdm", "cdiscpilot01-sap.txt": "sap", "dm.xpt": "sdtm"}
    assert staged["sdtmDomains"] == ["DM"] and "1 unreadable: DM" in staged["summary"], staged

    run.planner(broken_plan(work))
    run.step("check-plan", "check_plan.py")
    run.planner(FIXTURES / "plan")
    assert run.step("check-plan", "check_plan.py")["needsFix"] is False
    run.critic()
    run.output("review-plan", {"verdict": "revise", "reviewerComment": "Add a by-site disposition table."})
    recorded = run.step("record-review", "record_review.py")
    assert recorded["iteration"] == 1
    assert (run.workspace / "tlf-planning" / "attempts.json").is_file() is False, "a review round gets fresh attempts"
    line = json.loads((run.workspace / "tlf-planning" / "review-feedback.jsonl").read_text().splitlines()[-1])
    assert line["comment"] == "Add a by-site disposition table." and line["skill"] == "tlf-planner"

    run.planner(FIXTURES / "plan")
    assert run.step("check-plan", "check_plan.py")["attempt"] == 1
    run.critic()
    run.output("review-plan", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    kinds = {item["name"]: item["kind"] for item in result["package"]["files"]}
    assert kinds["usdm.json"] == "usdm" and kinds["dm.xpt"] == "sdtm" and kinds["review-feedback.jsonl"] == "review-feedback", kinds
    uploaded = [item for item in result["package"]["files"] if item["name"] == "usdm.json"][0]
    assert uploaded["producedBy"]["step"] == "upload-inputs" and "localPath" not in uploaded


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for test in (test_planned, test_gate_failure, test_upload_and_review):
            test(work)
            print(f"ok  {test.__name__}")


if __name__ == "__main__":
    main()
