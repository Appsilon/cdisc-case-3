"""End-to-end check of the plan-tlfs scripts, with fixture files standing in for the agents.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath, one shared /workspace). The planner's output is the CDISCPILOT01 plan
from the original UC3 run (tests/fixtures/plan).

  1. package mode, clean plan       -> data check passes, gate passes, html rendered, outcome planned, package kinds
  2. broken plan (orphan, bad trace, duplicate id, dropped endpoint) -> gate sends it back, then failed
  3. upload mode + a review round   -> files classified, comment recorded, attempts reset
  4. another study's SDTM (the 18-subject 'Zanomaline' set) -> data check fails, outcome data-mismatch
  5. the primary endpoints left blocked -> dataBlocked, outcome data-mismatch (not sent back to the planner)

Fixtures: pilot/ = the CDISCPILOT01 USDM (trimmed to what the checks read) with
its real DM / EX / TS / TA; synthetic/ = DM / TS / TA of the wrong set that fed
every run before 2026-11-13.

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
PILOT = FIXTURES / "pilot"
PILOT_SDTM = [PILOT / f"{domain}.xpt" for domain in ("dm", "ex", "ts", "ta")]


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
        target = self.workspace / "plan-tlfs" / "plan"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(plan_dir, target, ignore=shutil.ignore_patterns("coverage-report.md"))
        self.output("plan-tlfs", {"summary": "fixture plan"})

    def critic(self) -> None:
        audit = self.workspace / "plan-tlfs" / "audit"
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


def primary_planned(work: Path) -> Path:
    """The fixture plan was made on data without ADAS-Cog / CIBIC+; plan one output per primary efficacy endpoint."""
    target = work / "primary-planned"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(FIXTURES / "plan", target)
    plan = json.loads((target / "tlf-plan.json").read_text())
    for candidate_id, final_id in (("eff-END1-ancova-wk24-locf", "T-14-3.06"), ("eff-END2-anova-wk24", "T-14-3.07")):
        candidate = next(item for item in plan if item["candidate_id"] == candidate_id)
        candidate.update({"status": "planned", "final_id": final_id, "status_reason": None})
    (target / "tlf-plan.json").write_text(json.dumps(plan))
    with open(target / "tlf-index.md", "a", encoding="utf-8") as index:
        index.write("\n| T-14-3.06 | ADAS-Cog (11) primary analysis |\n| T-14-3.07 | CIBIC+ primary analysis |\n")
    return target


def test_planned(work: Path) -> None:
    run = Run(work / "planned")
    files = [entry(PILOT / "usdm.json", "usdm"), entry(FIXTURES / "cdiscpilot01-sap.txt", "sap")]
    files += [entry(path, "sdtm") for path in PILOT_SDTM + [FIXTURES / "sdtm" / "qsph.xpt"]]
    package = {"study": {"id": "CDISCPILOT01"}, "files": without_local(files)}
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": package})
    assert resolved["needsUpload"] is False and {item["kind"] for item in resolved["files"]} == {"usdm", "sap", "sdtm"}, resolved
    staged = run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    inputs = run.workspace / "plan-tlfs" / "inputs"
    assert (inputs / "usdm.json").is_file() and (inputs / "sap" / "cdiscpilot01-sap.txt").is_file(), staged
    assert staged["sdtmDomains"] == ["DM", "EX", "QSPH", "TA", "TS"], staged
    inventory = json.loads((inputs / "sdtm-inventory.json").read_text())["domains"]
    assert inventory["QSPH"]["records"] == 2 and inventory["QSPH"]["codes"]["QSCAT"]["values"] == ["PHQ-9"], inventory
    assert inventory["QSPH"]["codes"]["QSTESTCD"] == {"count": 2, "values": ["PHQ0101", "PHQ0102"]}, inventory

    study = run.step("check-study", "check_study.py")
    assert study["failed"] is False and study["counts"]["byArm"] == {"Placebo": 86, "Xanomeline High Dose": 84, "Xanomeline Low Dose": 84}, study
    assert {item["check"]: item["status"] for item in study["checks"]} == {
        "arm-count": "pass", "arms": "pass", "enrollment": "pass", "exposure": "pass", "trial-arms": "pass", "plansub": "pass", "title": "pass", "phase": "pass"}, study

    run.planner(primary_planned(work))
    checked = run.self_check()
    assert checked.returncode == 0 and checked.stdout.startswith("PASS"), checked.stdout
    assert (run.workspace / "plan-tlfs" / "attempts.json").is_file() is False, "self-check must not use an attempt"
    gate = run.step("check-plan", "check_plan.py")
    assert gate["needsFix"] is False and gate["dataBlocked"] is False and gate["counts"]["tables"] == 30, gate
    assert gate["counts"]["blockedEndpoints"] == ["Endpoint_6", "Endpoint_7", "Endpoint_8"] and gate["counts"]["blockedPrimary"] == [], gate
    page = (run.steps_dir / "check-plan" / "tlf-plan.html").read_text()
    assert "T-14-1.01" in page and "Flagged" in page and "Data checks" in page and "<script" not in page

    run.critic()
    run.output("review-plan", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "planned" and result["verdict"] == "clean-with-caveats", result
    kinds = sorted({item["kind"] for item in result["package"]["files"]})
    assert kinds == ["coverage-report", "sap", "sdtm", "study-model", "tlf-plan", "tlf-plan-view", "usdm"], kinds
    assert [item["name"] for item in result["package"]["files"] if item["kind"] == "tlf-plan"] == ["tlf-plan.json"]
    names = {item["name"] for item in result["files"]}
    assert {"study-model.json", "tlf-plan.json", "tlf-index.md", "tlf-plan.html", "coverage-report.md", "study-check.html"} <= names, names
    published = {item["name"]: item["downloadUrl"] for item in result["files"]}
    assert published["tlf-plan.json"].endswith("/output/check-plan/tlf-plan.json"), "publish the copy the gate checked"
    assert published["coverage-report.md"].endswith("/output/return-result/coverage-report.md"), published
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
    study = run.step("check-study", "check_study.py")
    assert study["failed"] is False and study["checks"][0]["check"] == "sdtm", "planning before any SDTM exists stays possible"
    run.planner(broken_plan(work))
    problems = None
    for attempt in (1, 2, 3):
        gate = run.step("check-plan", "check_plan.py")
        assert gate["needsFix"] is True and gate["attempt"] == attempt and gate["retry"] is (attempt < 3), gate
        problems = gate["problems"]
        feedback = json.loads((run.workspace / "plan-tlfs" / "feedback.json").read_text())
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
    broken = work / "lb.xpt"
    broken.write_bytes(b"not really xpt")
    define = work / "define.xml"
    define.write_text("<ODM/>")
    uploads = [entry(PILOT / "usdm.json", None), entry(FIXTURES / "cdiscpilot01-sap.txt", None), entry(PILOT / "dm.xpt", None),
               entry(PILOT / "ex.xpt", None), entry(broken, None), entry(define, None)]
    staged = run.step("stage-inputs", "stage_inputs.py", files=uploads)
    assert {item["name"]: item["kind"] for item in staged["inputFiles"]} == {"usdm.json": "usdm", "cdiscpilot01-sap.txt": "sap", "dm.xpt": "sdtm",
                                                                         "ex.xpt": "sdtm", "lb.xpt": "sdtm", "define.xml": "sdtm-define"}
    assert staged["sdtmDomains"] == ["DM", "EX", "LB"] and "1 unreadable: LB" in staged["summary"], staged
    assert run.step("check-study", "check_study.py")["failed"] is False

    run.planner(broken_plan(work))
    run.step("check-plan", "check_plan.py")
    run.planner(primary_planned(work))
    assert run.step("check-plan", "check_plan.py")["needsFix"] is False
    run.critic()
    run.output("review-plan", {"verdict": "revise", "reviewerComment": "Add a by-site disposition table."})
    recorded = run.step("record-review", "record_review.py")
    assert recorded["iteration"] == 1
    assert (run.workspace / "plan-tlfs" / "attempts.json").is_file() is False, "a review round gets fresh attempts"
    line = json.loads((run.workspace / "plan-tlfs" / "review-feedback.jsonl").read_text().splitlines()[-1])
    assert line["comment"] == "Add a by-site disposition table." and line["skill"] == "tlf-planner"

    run.planner(primary_planned(work))
    assert run.step("check-plan", "check_plan.py")["attempt"] == 1
    run.critic()
    run.output("review-plan", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    kinds = {item["name"]: item["kind"] for item in result["package"]["files"]}
    assert kinds["usdm.json"] == "usdm" and kinds["dm.xpt"] == "sdtm" and kinds["define.xml"] == "sdtm-define" and kinds["review-feedback.jsonl"] == "review-feedback-plan-tlfs", kinds
    uploaded = [item for item in result["package"]["files"] if item["name"] == "usdm.json"][0]
    assert uploaded["producedBy"]["step"] == "upload-inputs" and "localPath" not in uploaded


def test_wrong_study(work: Path) -> None:
    run = Run(work / "wrong-study")
    files = [entry(PILOT / "usdm.json", "usdm")] + [entry(path, "sdtm") for path in sorted((FIXTURES / "synthetic").glob("*.xpt"))]
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local(files)}})
    run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    study = run.step("check-study", "check_study.py")
    statuses = {item["check"]: item["status"] for item in study["checks"]}
    assert study["failed"] is True and statuses["arms"] == "warn" and statuses["arm-count"] == "pass", study
    assert statuses["enrollment"] == "fail" and statuses["exposure"] == "fail", study
    assert "17 randomised subjects vs 300 planned" in study["summary"], study["summary"]
    assert any("Zanomaline" in item["detail"] for item in study["checks"] if item["check"] == "arms"), study
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "data-mismatch" and "study-check.html" in {item["name"] for item in result["files"]}, result
    assert "tlf-plan" not in {item["kind"] for item in result["package"]["files"]}
    assert result["package"]["history"][-1]["outcome"] == "data-mismatch"


def test_primary_blocked(work: Path) -> None:
    run = Run(work / "primary-blocked")
    files = [entry(PILOT / "usdm.json", "usdm")] + [entry(path, "sdtm") for path in PILOT_SDTM]
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local(files)}})
    run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    assert run.step("check-study", "check_study.py")["failed"] is False
    run.planner(FIXTURES / "plan")
    assert "Objective(s) Objective_1 would have no primary endpoint left" in run.self_check().stdout
    gate = run.step("check-plan", "check_plan.py")
    assert gate["needsFix"] is False and gate["dataBlocked"] is True and gate["counts"]["blockedPrimary"] == ["Endpoint_1", "Endpoint_2"], gate
    assert gate["counts"]["unanswerableObjectives"] == ["Objective_1"], gate
    assert (run.workspace / "plan-tlfs" / "feedback.json").is_file() is False, "the planner cannot add data: not sent back"
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "data-mismatch" and "Endpoint_1" in result["summary"], result
    assert {"study-check.html", "tlf-plan.json"} <= {item["name"] for item in result["files"]}, result["files"]

    clarify = work / "primary-clarify"
    shutil.rmtree(clarify, ignore_errors=True)
    shutil.copytree(FIXTURES / "plan", clarify)
    plan = json.loads((clarify / "tlf-plan.json").read_text())
    for candidate in plan:
        if "Endpoint_1" in (candidate["traces_to"].get("endpoint_ids") or []):
            candidate.update({"status": "needs-clarification", "status_reason": "Which LOCF window does the SAP mean?"})
    (clarify / "tlf-plan.json").write_text(json.dumps(plan))
    run.planner(clarify)
    gate = run.step("check-plan", "check_plan.py")
    assert gate["counts"]["blockedPrimary"] == ["Endpoint_2"], "a clarification item goes to the statistician, not to data-mismatch"
    assert gate["dataBlocked"] is False and "PRIMARY endpoint(s) Endpoint_2" in gate["summary"], \
        "an objective with a primary endpoint left (here one in clarification) goes to the statistician"


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for test in (test_planned, test_gate_failure, test_upload_and_review, test_wrong_study, test_primary_blocked):
            test(work)
            print(f"ok  {test.__name__}")


if __name__ == "__main__":
    main()
