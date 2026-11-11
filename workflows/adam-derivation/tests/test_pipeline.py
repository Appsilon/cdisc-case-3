"""End-to-end check of the adam-derivation scripts with real R and real SDTM.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath, one shared /workspace) and stands in for the agent with the fixture
programs in tests/fixtures/programs:

  1. package mode, clean programs  -> outcome derived; lineage, define, package kinds
  2. an untagged column and an untagged extra column -> check-lineage sends it back (retry),
     then, attempts used up -> outcome failed
  3. fix loop: package carrying programs + CORE dispositions -> fixMode, findings staged

Needs R with haven, jsonlite, dplyr and the SDTM folder:
  SDTM_DIR=$HOME/Repo/FULL_WORKFLOW/inputs/sdtm python3 tests/test_pipeline.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
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
        shutil.copytree(ARTIFACTS, root / "artifacts")
        for helper in SHARED.glob("*.py"):
            shutil.copyfile(helper, self.scripts / helper.name)
        self.variables: dict[str, dict] = {}
        self.previous: dict = {}

    def environment(self, step_id: str) -> dict:
        return {**os.environ, "MEDIFORCE_OUTPUT_DIR": str(self.steps_dir / step_id), "MEDIFORCE_STEP_OUTPUTS_DIR": str(self.steps_dir),
                "MEDIFORCE_WORKSPACE_DIR": str(self.workspace), "RUN_ID": f"run-{self.root.name}", "STEP_ID": step_id}

    def step(self, step_id: str, script: str, params: dict | None = None, files: list[dict] | None = None, expect_failure: bool = False) -> dict:
        output_dir = self.steps_dir / step_id
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True)
        step_input = {**self.previous, "steps": self.variables, **(params or {})}
        if files is not None:
            step_input["files"] = files
        (output_dir / "input.json").write_text(json.dumps(step_input), encoding="utf-8")
        completed = subprocess.run([sys.executable, str(self.scripts / script)], env=self.environment(step_id), capture_output=True, text=True)
        result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
        if expect_failure:
            assert completed.returncode != 0, f"{step_id} should have failed"
            return result
        if completed.returncode != 0:
            raise AssertionError(f"{step_id} failed: {result.get('error')}\n{completed.stderr[-3000:]}")
        self.variables[step_id] = result
        self.previous = result
        return result

    def agent(self, programs: Path) -> None:
        """The author-programs step: put programs in /workspace/programs."""
        target = self.workspace / "programs"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(programs, target)
        output = {"programs": sorted(path.name for path in target.glob("*.R")), "summary": "fixture programs"}
        self.variables["author-programs"] = output
        self.previous = output


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(path: Path, kind: str) -> dict:
    return {"name": path.name, "downloadUrl": f"/api/attachments/{path.name}/blob", "kind": kind, "sha256": sha(path), "localPath": str(path)}


def package_for(sdtm_dir: Path, spec: Path, extra: list[dict] | None = None) -> dict:
    files = [entry(path, "sdtm") for path in sorted(sdtm_dir.glob("*.xpt"))] + [entry(sdtm_dir / "define.xml", "sdtm-define"), entry(spec, "adam-spec")]
    return {"study": {"id": "CDISCPILOT01"}, "profile": {"adamig": "1-3"}, "files": files + (extra or [])}


def without_local(package: dict) -> dict:
    return {**package, "files": [{key: value for key, value in item.items() if key != "localPath"} for item in package["files"]]}


def run_gates(run: Run) -> tuple[dict, dict | None]:
    executed = run.step("execute-programs", "execute_programs.py")
    if executed["needsFix"]:
        return executed, None
    return executed, run.step("check-lineage", "check_lineage.py")


def test_derived(work: Path, sdtm_dir: Path) -> None:
    run = Run(work / "derived")
    package = package_for(sdtm_dir, FIXTURES / "adam-spec.json")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": without_local(package)})
    assert resolved["needsUpload"] is False, resolved
    local = {item["name"]: item["localPath"] for item in package["files"]}
    staged = run.step("stage-inputs", "stage_inputs.py", files=[{**item, "localPath": local[item["name"]]} for item in resolved["files"]])
    assert staged["fixMode"] is False and "DM" in staged["sdtm"], staged
    run.agent(FIXTURES / "programs")

    check = subprocess.run([sys.executable, str(run.scripts / "self_check.py")], env=run.environment("author-programs"), capture_output=True, text=True)
    assert check.stdout.strip().endswith("PASS"), check.stdout + check.stderr
    assert (run.workspace / "adam-derivation" / "attempts.json").is_file() is False, "self-check must not use an attempt"

    executed, lineage_gate = run_gates(run)
    assert executed["needsFix"] is False, executed["problems"]
    assert lineage_gate["needsFix"] is False, lineage_gate["problems"]
    lineage = json.loads((run.steps_dir / "check-lineage" / "lineage.json").read_text(encoding="utf-8"))
    trtsdt = next(item for item in lineage["variables"] if item["dataset"] == "ADSL" and item["variable"] == "TRTSDT")
    assert trtsdt["program"] == "adsl.R" and trtsdt["sources"] == ["EX.EXSTDTC", "EX.EXDOSE"] and trtsdt["spec"] == "ADSL.TRTSDT", trtsdt
    program_lines = (run.workspace / "programs" / "adsl.R").read_text(encoding="utf-8").splitlines()
    assert "TRTSDT" in "\n".join(program_lines[trtsdt["lines"][0] - 1:trtsdt["lines"][1]]), trtsdt["lines"]
    age = next(item for item in lineage["variables"] if item["variable"] == "AGE")
    assert age["origin"] == "Predecessor" and age["sources"] == ["DM.AGE"], age
    assert lineage["consumers"]["ADSL.SAFFL"] == ["T-14.1.1", "T-14.3.1"], lineage["consumers"]

    run.step("generate-define", "generate_define.py")
    define = ElementTree.parse(run.steps_dir / "generate-define" / "define.xml").getroot()
    namespaces = {"odm": "http://www.cdisc.org/ns/odm/v1.3", "def": "http://www.cdisc.org/ns/def/v2.1"}
    assert {group.get("Name") for group in define.iter(f"{{{namespaces['odm']}}}ItemGroupDef")} == {"ADSL", "ADAE", "ADVS"}
    method = next(item for item in define.iter(f"{{{namespaces['odm']}}}MethodDef") if item.get("OID") == "MT.ADSL.TRTSDT")
    assert "adsl.R lines" in "".join(method.itertext()), "".join(method.itertext())
    item_defs = {item.get("OID"): item for item in define.iter(f"{{{namespaces['odm']}}}ItemDef")}
    assert item_defs["IT.ADSL.TRTSDT"].get("Length") == "8" and item_defs["IT.ADSL.TRTSDT"].get("DataType") == "integer"
    assert all(item.get("Length") for item in item_defs.values()), "every ItemDef needs a Length"

    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "derived", result["summary"]
    kinds = sorted({item["kind"] for item in result["package"]["files"]})
    assert {"adam", "adam-program", "adam-log", "lineage", "adam-define", "sdtm", "adam-spec"} <= set(kinds), kinds
    assert all(item["downloadUrl"].startswith(("/api/runs/", "/api/attachments/")) for item in result["package"]["files"])
    print("  derived:", result["summary"])


def test_gate_retry_then_failed(work: Path, sdtm_dir: Path) -> None:
    run = Run(work / "broken")
    package = package_for(sdtm_dir, FIXTURES / "adam-spec.json")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": without_local(package)})
    local = {item["name"]: item["localPath"] for item in package["files"]}
    run.step("stage-inputs", "stage_inputs.py", files=[{**item, "localPath": local[item["name"]]} for item in resolved["files"]])

    broken = work / "broken-programs"
    shutil.copytree(FIXTURES / "programs", broken)
    adae = broken / "adae.R"
    text = adae.read_text(encoding="utf-8")
    adae.write_text(text.replace("# @derive ADAE.AESEV origin=Predecessor src=AE.*\n", "") + "\n# stray column without a tag\nadae$EXTRA <- 1\nattr(adae$EXTRA, \"label\") <- \"Extra\"\nsaveRDS(adae, file.path(Sys.getenv(\"ADAM_DIR\"), \"adae.rds\"))\n", encoding="utf-8")

    for attempt in range(1, 4):
        run.agent(broken)
        executed, lineage_gate = run_gates(run)
        assert executed["needsFix"] is False, executed["problems"]
        assert lineage_gate["needsFix"] is True and lineage_gate["attempt"] == attempt, lineage_gate
        problems = "\n".join(lineage_gate["problems"])
        assert "no @derive tag for column(s) AESEV, EXTRA" in problems, problems
        feedback = json.loads((run.workspace / "adam-derivation" / "feedback.json").read_text(encoding="utf-8"))
        assert feedback["step"] == "check-lineage" and feedback["problems"] == lineage_gate["problems"]
        assert lineage_gate["retry"] is (attempt < 3), lineage_gate
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "failed" and result["attempts"] == 3, result["summary"]
    assert {item["kind"] for item in result["files"]} == {"adam-program", "adam-log"}
    assert not [item for item in result["package"]["files"] if item["kind"] == "adam"]
    print("  failed:", result["summary"][:160])


def test_fix_loop_staging(work: Path, sdtm_dir: Path) -> None:
    run = Run(work / "fix")
    dispositions = work / "core-dispositions-adamig.json"
    dispositions.write_text(json.dumps({"standard": "adamig", "dispositions": {
        "MF-ADAM-004|ADSL": {"rule": "MF-ADAM-004", "dataset": "ADSL", "issues": "2", "disposition": "fix", "justification": ""},
        "MF-ADAM-001|ADAE": {"rule": "MF-ADAM-001", "dataset": "ADAE", "issues": "1", "disposition": "justified", "justification": "ok"},
        "MF-ADAM-002|ADAE": {"rule": "MF-ADAM-002", "dataset": "ADAE", "issues": "4", "disposition": "fix", "justification": "fixed since"},
    }}), encoding="utf-8")
    report = work / "core-report.json"
    report.write_text(json.dumps({"Issue_Details": [
        {"core_id": "MF-ADAM-004", "dataset": "ADSL", "message": "TRTSDT missing for a safety subject", "USUBJID": "CDISC003", "row": 3, "variables": ["TRTSDT", "SAFFL"], "values": ["", "Y"]},
    ]}), encoding="utf-8")
    lineage = work / "lineage.json"
    lineage.write_text(json.dumps({"variables": [{"dataset": "ADSL", "variable": "TRTSDT", "program": "adsl.R", "lines": [1, 2]}]}), encoding="utf-8")
    extra = [entry(FIXTURES / "programs" / "adsl.R", "adam-program"), entry(FIXTURES / "programs" / "adae.R", "adam-program"),
             entry(lineage, "lineage"), entry(dispositions, "core-dispositions-adamig"), entry(report, "core-report-adamig"),
             {**entry(report, "core-report-adamig"), "name": "core-report.html"}]
    package = package_for(sdtm_dir, FIXTURES / "adam-spec.json", extra)
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": without_local(package)})
    names = [item["name"] for item in resolved["files"]]
    assert "core-report.json" in names and "core-report.html" not in names, names
    local = {item["name"]: item["localPath"] for item in package["files"]}
    staged = run.step("stage-inputs", "stage_inputs.py", files=[{**item, "localPath": local[item["name"]]} for item in resolved["files"]])
    assert staged["fixMode"] is True and staged["findings"] == 1, staged
    findings = json.loads((run.workspace / "adam-derivation" / "inputs" / "core-findings.json").read_text(encoding="utf-8"))["findings"]
    assert findings[0]["rule"] == "MF-ADAM-004" and findings[0]["examples"][0]["USUBJID"] == "CDISC003", findings
    assert (run.workspace / "programs" / "adsl.R").is_file() and (run.workspace / "adam-derivation" / "inputs" / "previous-lineage.json").is_file()
    print("  fix loop:", staged["summary"])

    # Dispositions without programs (e.g. after an SDTM re-upload dropped them): not a fix loop.
    orphan = Run(work / "orphan")
    package = package_for(sdtm_dir, FIXTURES / "adam-spec.json", [entry(dispositions, "core-dispositions-adamig"), entry(report, "core-report-adamig")])
    resolved = orphan.step("resolve-inputs", "resolve_inputs.py", {"package": without_local(package)})
    local = {item["name"]: item["localPath"] for item in package["files"]}
    staged = orphan.step("stage-inputs", "stage_inputs.py", files=[{**item, "localPath": local[item["name"]]} for item in resolved["files"]])
    findings = json.loads((orphan.workspace / "adam-derivation" / "inputs" / "core-findings.json").read_text(encoding="utf-8"))["findings"]
    assert staged["fixMode"] is False and findings == [], (staged, findings)


def test_upload_mode(work: Path, sdtm_dir: Path) -> None:
    run = Run(work / "upload")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {}})
    assert resolved["needsUpload"] is True
    uploads = [{key: value for key, value in entry(path, "x").items() if key != "kind"} for path in [*sorted(sdtm_dir.glob("*.xpt")), sdtm_dir / "define.xml", FIXTURES / "adam-spec.json"]]
    staged = run.step("stage-inputs", "stage_inputs.py", files=uploads)
    kinds = {item["kind"] for item in staged["inputFiles"]}
    assert kinds == {"sdtm", "sdtm-define", "adam-spec"}, kinds
    print("  upload:", staged["summary"])


def r_libraries() -> str:
    """Programs run with Rscript --vanilla, which skips ~/.Renviron; hand the local library paths over explicitly."""
    completed = subprocess.run(["Rscript", "-e", "cat(.libPaths(), sep = ':')"], capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def main() -> None:
    os.environ["R_LIBS"] = r_libraries()
    sdtm = os.environ.get("SDTM_DIR")
    if not sdtm:
        raise SystemExit("Set SDTM_DIR (see the module docstring).")
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for test in (test_upload_mode, test_fix_loop_staging, test_derived, test_gate_retry_then_failed):
            print(test.__name__)
            test(work, Path(sdtm))
    print("all passed")


if __name__ == "__main__":
    main()
