"""End-to-end check of the analysis-specification scripts, with fixture specs standing in for the agent.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath, one shared /workspace). The plan is tlf-planning's CDISCPILOT01
fixture; the specs are the UC3 run's specs with its gate findings corrected
(tests/fixtures/specs). The ARS check uses the carried LDM schema.

  1. package mode, clean specs   -> gate passes, specs.html, outcome specified, package kinds
  2. defects (schema, dangling id, missing output, unknown variable, undelivered SDTM,
     non-literal PARAMCD) -> each reported; three attempts -> failed
  3. upload mode + review round  -> classification, comment recorded, attempts reset

Needs R with haven + jsonlite (SDTM inventory) and Python jsonschema:
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
PLAN_FIXTURES = HERE.parent.parent / "tlf-planning" / "tests" / "fixtures"


class Run:
    """One simulated workflow run: a worktree (/workspace), its step outputs and variables."""

    def __init__(self, root: Path):
        self.root = root
        self.workspace = root / "workspace"
        self.steps_dir = self.workspace / ".mediforce" / "output"
        self.scripts = root / "artifacts" / "scripts"
        shutil.copytree(ARTIFACTS, root / "artifacts", ignore=shutil.ignore_patterns("skills"))
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

    def agent(self, specs_dir: Path) -> None:
        target = self.workspace / "analysis-specification" / "specs"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(specs_dir, target)
        self.output("build-specs", {"summary": "fixture specs"})

    def self_check(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.scripts / "self_check.py")], env=self.environment("build-specs"), capture_output=True, text=True)


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


def sdtm_files(work: Path) -> list[Path]:
    """Every domain the fixture ADaM spec reads, as tiny real XPT files."""
    spec = json.loads((FIXTURES / "specs" / "adam-spec.json").read_text())
    domains = sorted({str(source).lower() for dataset in spec["datasets"] for source in dataset.get("sdtm_source") or []})
    folder = work / "sdtm"
    if folder.is_dir() is False:
        folder.mkdir()
        program = "for (domain in commandArgs(TRUE)[-1]) haven::write_xpt(data.frame(STUDYID = 'X', USUBJID = '1'), " \
                  "file.path(commandArgs(TRUE)[1], paste0(domain, '.xpt')), version = 5)"
        subprocess.run(["Rscript", "-e", program, str(folder), *domains], check=True, capture_output=True)
    return sorted(folder.glob("*.xpt"))


def package_files(work: Path) -> list[dict]:
    return [entry(PLAN_FIXTURES / "plan" / "tlf-plan.json", "tlf-plan"), entry(PLAN_FIXTURES / "plan" / "study-model.json", "study-model"),
            entry(PLAN_FIXTURES / "plan" / "tlf-index.md", "tlf-plan")] + [entry(path, "sdtm") for path in sdtm_files(work)]


def test_specified(work: Path) -> None:
    run = Run(work / "specified")
    files = package_files(work)
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local(files)}})
    assert [item["name"] for item in resolved["files"][:2]] == ["tlf-plan.json", "study-model.json"], resolved
    assert "tlf-index.md" not in {item["name"] for item in resolved["files"]}
    staged = run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    assert staged["plannedOutputs"] == 29 and "QSPH" in staged["sdtmDomains"], staged

    run.agent(FIXTURES / "specs")
    checked = run.self_check()
    assert checked.returncode == 0 and checked.stdout.startswith("PASS"), checked.stdout
    assert (run.workspace / "analysis-specification" / "attempts.json").is_file() is False
    gate = run.step("check-specs", "check_specs.py")
    assert gate["needsFix"] is False and gate["counts"]["analyses"] == 29, gate
    page = (run.steps_dir / "check-specs" / "specs.html").read_text()
    assert "14-3.01" in page and "ADQSPHQ" in page and "<script" not in page

    run.output("review-specs", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "specified", result
    kinds = {item["name"]: item["kind"] for item in result["package"]["files"]}
    assert kinds["analysis-spec.json"] == "analysis-spec" and kinds["reporting-event.json"] == "ars" and kinds["adam-spec.json"] == "adam-spec", kinds
    assert kinds["tlf-plan.json"] == "tlf-plan" and kinds["specs.html"] == "analysis-spec"


def broken_specs(work: Path) -> Path:
    target = work / "broken-specs"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(FIXTURES / "specs", target)
    event = json.loads((target / "reporting-event.json").read_text())
    event["analyses"][0]["methodId"] = "MTH.NOPE"
    event["outputs"] = [item for item in event["outputs"] if item["id"] != "OUT.T-14-3.01"]
    event["analysisSets"][0]["level"] = "one"
    (target / "reporting-event.json").write_text(json.dumps(event))
    spec = json.loads((target / "adam-spec.json").read_text())
    adlb = [item for item in spec["datasets"] if item["name"] == "ADLB"][0]
    adlb["parameters"].append({"paramcd": "ALT/AST"})
    adlb["sdtm_source"].append("MB")
    (target / "adam-spec.json").write_text(json.dumps(spec))
    entries = json.loads((target / "analysis-spec.json").read_text())
    entries[0]["groupingFactor"]["variable"] = "TRTZZ"
    entries = [item for item in entries if item["table_id"] != "14-5.01"]
    (target / "analysis-spec.json").write_text(json.dumps(entries))
    return target


def test_gate_failure(work: Path) -> None:
    run = Run(work / "broken")
    files = package_files(work)
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local(files)}})
    run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    run.agent(broken_specs(work))
    for attempt in (1, 2, 3):
        gate = run.step("check-specs", "check_specs.py")
        assert gate["needsFix"] is True and gate["attempt"] == attempt and gate["retry"] is (attempt < 3), gate
    text = "\n".join(gate["problems"])
    for expected in ("MTH.NOPE", "no output OUT.T-14-3.01", "analysisSets/0/level", "'ALT/AST'", "sdtm_source MB was not delivered",
                     "TRTZZ", "no entry for planned output(s) 14-5.01"):
        assert expected in text, (expected, text)
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "failed" and "adam-spec" not in {item["kind"] for item in result["package"]["files"]}, result


def test_upload_and_review(work: Path) -> None:
    run = Run(work / "upload")
    assert run.step("resolve-inputs", "resolve_inputs.py", {"package": {}})["needsUpload"] is True
    uploads = [entry(PLAN_FIXTURES / "plan" / "tlf-plan.json", None), entry(PLAN_FIXTURES / "plan" / "study-model.json", None),
               entry(PLAN_FIXTURES / "usdm.json", None)] + [entry(path, None) for path in sdtm_files(work)]
    staged = run.step("stage-inputs", "stage_inputs.py", files=uploads)
    classified = {item["name"]: item["kind"] for item in staged["inputFiles"]}
    assert classified["tlf-plan.json"] == "tlf-plan" and classified["study-model.json"] == "study-model" and classified["usdm.json"] == "usdm"
    assert classified["ae.xpt"] == "sdtm", classified
    run.agent(FIXTURES / "specs")
    assert run.step("check-specs", "check_specs.py")["needsFix"] is False
    run.output("review-specs", {"verdict": "revise", "reviewerComment": "Use OC as the primary imputation for 14-3.01."})
    assert run.step("record-review", "record_review.py")["iteration"] == 1
    feedback = run.workspace / "analysis-specification" / "review-feedback.jsonl"
    assert json.loads(feedback.read_text().splitlines()[-1])["skill"] == "tlf-analysis-spec"
    assert (run.workspace / "analysis-specification" / "attempts.json").is_file() is False
    run.agent(FIXTURES / "specs")
    assert run.step("check-specs", "check_specs.py")["attempt"] == 1
    run.output("review-specs", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    kinds = {item["name"]: item["kind"] for item in result["package"]["files"]}
    assert kinds["review-feedback.jsonl"] == "review-feedback-analysis-specification" and kinds["tlf-plan.json"] == "tlf-plan", kinds


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for test in (test_specified, test_gate_failure, test_upload_and_review):
            test(work)
            print(f"ok  {test.__name__}")


if __name__ == "__main__":
    main()
