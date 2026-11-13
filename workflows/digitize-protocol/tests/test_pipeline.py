"""End-to-end check of the digitize-protocol scripts, with fixture files standing in for the agent and the CORE child.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath, one shared /workspace). The agent's output is a CDISCPILOT01
extraction (tests/fixtures/usdm) made by the protocol-to-usdm skill.

  1. package mode, clean extraction -> self-check PASS without an attempt, gate passes, review page, CORE accepts, digitized
  2. broken extraction (dangling reference, missing criteria, bad citations) -> three attempts, then failed
  3. malformed shape (a string among the objectives, a Code missing fields) -> gate problems, not a crash
  4. upload mode, CORE rejects once (a stale fix from an earlier round ignored), the reviewer asks for a change
     -> core feedback, dispositions + issue index carried, CORE count restarted, digitized
  5. CORE keeps rejecting -> failed after the third round

Needs the CDISCPILOT01 protocol PDF (not committed: Eli Lilly copyright) and pypdf + jsonschema:
  PROTOCOL_PDF=<cdiscpilot01-protocol.pdf> python3 tests/test_pipeline.py
The USDM 4.0 schema is fetched once from DDF-RA at the commit the Dockerfile pins.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parent / "artifacts"
SHARED = HERE.parent.parent / "shared"
FIXTURES = HERE / "fixtures"
PROTOCOL_PDF = Path(os.environ.get("PROTOCOL_PDF", Path.home() / "Repo/cdisc-case-3/handover/cdiscpilot01-protocol.pdf"))

sys.path.insert(0, str(HERE))
from compare_usdm import compare  # noqa: E402


def usdm_api() -> Path:
    """The schema the image bakes in: same commit and sha256 as artifacts/Dockerfile."""
    dockerfile = (ARTIFACTS / "Dockerfile").read_text(encoding="utf-8")
    commit = re.search(r"DDF_RA_COMMIT=(\w+)", dockerfile).group(1)
    digest = re.search(r"USDM_API_SHA256=(\w+)", dockerfile).group(1)
    cached = Path.home() / ".cache" / "mediforce" / f"USDM_API-{commit[:12]}.json"
    if cached.is_file() is False:
        data = urllib.request.urlopen(f"https://raw.githubusercontent.com/cdisc-org/DDF-RA/{commit}/Deliverables/API/USDM_API.json").read()
        assert hashlib.sha256(data).hexdigest() == digest, "USDM_API.json does not match the Dockerfile's sha256"
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    return cached


class Run:
    """One simulated workflow run: a worktree (/workspace), its step outputs and variables."""

    def __init__(self, root: Path):
        self.root = root
        self.workspace = root / "workspace"
        self.work = self.workspace / "digitize-protocol"
        self.steps_dir = self.workspace / ".mediforce" / "output"
        self.scripts = root / "artifacts" / "scripts"
        shutil.copytree(ARTIFACTS / "scripts", self.scripts)
        for helper in SHARED.glob("*.py"):
            shutil.copyfile(helper, self.scripts / helper.name)
        self.variables: dict[str, dict] = {}
        self.previous: dict = {}

    def environment(self, step_id: str) -> dict:
        return {**os.environ, "MEDIFORCE_OUTPUT_DIR": str(self.steps_dir / step_id), "MEDIFORCE_STEP_OUTPUTS_DIR": str(self.steps_dir),
                "MEDIFORCE_WORKSPACE_DIR": str(self.workspace), "RUN_ID": f"run-{self.root.name}", "STEP_ID": step_id,
                "USDM_API_SOURCE": str(usdm_api())}

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
        if (completed.returncode != 0) is not expect_failure:
            raise AssertionError(f"{step_id} exit {completed.returncode}: {result.get('error')}\n{completed.stderr[-3000:]}")
        if expect_failure is False:
            self.variables[step_id] = result
            self.previous = result
        return result

    def output(self, step_id: str, result: dict) -> None:
        """A non-script step (agent, human, child run): record its output."""
        self.variables[step_id] = result
        self.previous = result

    def agent(self, usdm_dir: Path) -> None:
        target = self.work / "usdm"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(usdm_dir, target)
        self.output("extract-usdm", {"summary": "fixture extraction"})

    def self_check(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.scripts / "self_check.py")], env=self.environment("extract-usdm"), capture_output=True, text=True)

    def core(self, outcome: str, core_run: str, fix_rules: tuple[str, ...] = (), stale_fix: str = "") -> dict:
        """The validate-with-core child: report + dispositions published in its run, its package returned."""
        child_dir = self.root / core_run
        child_dir.mkdir(parents=True, exist_ok=True)
        report = {"Issue_Details": [{"core_id": rule, "cdisc_rule_id": "DDF00099", "message": f"{rule} message", "entity": "Code",
                                     "instance_id": "Code_9", "path": "/study/versions/0/studyDesigns/0/objectives/0/level",
                                     "attributes": ["code", "decode"], "values": ["C85826", "Primary Objective"]} for rule in fix_rules]}
        dispositions = {"standard": "usdm", "dispositions": {
            f"{rule}|None": {"rule": rule, "dataset": "None", "issues": 1, "disposition": "fix", "justification": "Use the DDF codelist.", "runId": core_run}
            for rule in fix_rules} | {"CORE-001076|None": {"rule": "CORE-001076", "disposition": "justified", "justification": "No BCs in v1.", "runId": core_run}}}
        if stale_fix:  # a finding marked fix in an earlier round that this round no longer reports
            dispositions["dispositions"][f"{stale_fix}|None"] = {"rule": stale_fix, "disposition": "fix", "justification": "", "runId": "core-run-earlier"}
        (child_dir / "core-report.json").write_text(json.dumps(report))
        (child_dir / "core-dispositions-usdm.json").write_text(json.dumps(dispositions))
        (child_dir / "core-issue-index-usdm.json").write_text(json.dumps({"standard": "usdm", "keys": [f"{rule}|None||" for rule in fix_rules]}))
        produced = {"workflow": "validate-with-core", "runId": core_run, "step": "decide"}
        files = [{**entry(child_dir / "core-report.json", "core-report-usdm"), "producedBy": produced},
                 {**entry(child_dir / "core-dispositions-usdm.json", "core-dispositions-usdm"), "producedBy": produced},
                 {**entry(child_dir / "core-issue-index-usdm.json", "core-issue-index-usdm"), "producedBy": produced}]
        package = dict(self.variables["check-usdm"]["package"])
        package["files"] = [item for item in package["files"]
                            if item["kind"] not in ("core-report-usdm", "core-dispositions-usdm", "core-issue-index-usdm")] + without_local(files)
        package["history"] = list(package.get("history") or []) + [{"workflow": "validate-with-core", "runId": core_run, "outcome": outcome}]
        self.output("validate-with-core", {"status": "completed", "output": {"outcome": outcome, "summary": f"{outcome.upper()}: usdm 4-0",
                                                                       "files": without_local(files), "package": package}})
        return {item["name"]: item["localPath"] for item in files}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(path: Path, kind: str | None) -> dict:
    item = {"name": path.name, "downloadUrl": f"/api/attachments/{path.name}/blob", "sha256": sha(path), "localPath": str(path)}
    return {**item, "kind": kind} if kind else item


def without_local(files: list[dict]) -> list[dict]:
    return [{key: value for key, value in item.items() if key != "localPath"} for item in files]


def with_local(files: list[dict], local: dict[str, str]) -> list[dict]:
    return [{**item, "localPath": local[item["name"]]} for item in files]


def protocol_entry(work: Path, name: str, kind: str | None) -> dict:
    target = work / name
    shutil.copyfile(PROTOCOL_PDF, target)
    return entry(target, kind)


def test_digitized(work: Path) -> None:
    run = Run(work / "digitized")
    protocol = protocol_entry(work, "cdiscpilot01-protocol.pdf", "protocol")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"study": {"id": "CDISCPILOT01"}, "files": without_local([protocol])}})
    assert resolved["needsUpload"] is False and [item["kind"] for item in resolved["files"]] == ["protocol"], resolved
    staged = run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], {protocol["name"]: protocol["localPath"]}))
    assert staged["documents"] == {"protocol": 51}, staged
    assert "Primary Objectives" in (run.work / "inputs" / "protocol" / "pages" / "page-007.txt").read_text()

    run.agent(FIXTURES / "usdm")
    checked = run.self_check()
    assert checked.returncode == 0 and checked.stdout.startswith("PASS"), checked.stdout[-3000:]
    assert (run.work / "attempts.json").is_file() is False, "self-check must not use an attempt"
    gate = run.step("check-usdm", "check_usdm.py")
    assert gate["needsFix"] is False and gate["counts"]["citations"] > 50, gate
    assert sorted(item["kind"] for item in gate["package"]["files"]) == ["protocol", "usdm", "usdm-citations"], gate["package"]
    run.core("accepted", "core-run-1")
    run.step("prepare-review", "prepare_review.py")
    page = (run.steps_dir / "prepare-review" / "usdm-review.html").read_text()
    assert "Schedule of activities" in page and "p. 7" in page and "ACCEPTED: usdm 4-0" in page and "<script" not in page
    run.output("review-usdm", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "digitized", result
    kinds = sorted({item["kind"] for item in result["package"]["files"]})
    assert kinds == ["core-dispositions-usdm", "core-issue-index-usdm", "core-report-usdm", "protocol", "usdm", "usdm-citations", "usdm-view"], kinds
    published = {item["name"]: item["downloadUrl"] for item in result["files"]}
    assert published["usdm.json"].endswith("/output/check-usdm/usdm.json"), "publish the copy the gate checked"
    assert published["usdm-review.html"].endswith("/output/prepare-review/usdm-review.html"), published
    assert [item["outcome"] for item in result["package"]["history"]] == ["accepted", "digitized"], result["package"]["history"]


def broken_extraction(work: Path) -> Path:
    target = work / "broken-usdm"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(FIXTURES / "usdm", target)
    document = json.loads((target / "usdm.json").read_text())
    citations = json.loads((target / "usdm-citations.json").read_text())
    design = document["study"]["versions"][0]["studyDesigns"][0]
    design["studyCells"][0]["armId"] = "StudyArm_99"
    design["eligibilityCriteria"] = [item for item in design["eligibilityCriteria"] if item["category"]["code"] != "C25370"]
    first_objective = design["objectives"][0]["id"]
    citations[first_objective] = {"page": 7, "quote": "This sentence is not in the protocol at all."}
    del citations[design["encounters"][0]["id"]]
    (target / "usdm.json").write_text(json.dumps(document))
    (target / "usdm-citations.json").write_text(json.dumps(citations))
    return target


def test_gate_failure(work: Path) -> None:
    run = Run(work / "broken")
    protocol = protocol_entry(work, "cdiscpilot01-protocol.pdf", "protocol")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local([protocol])}})
    run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], {protocol["name"]: protocol["localPath"]}))
    run.agent(broken_extraction(work))
    problems: list[str] = []
    for attempt in (1, 2, 3):
        gate = run.step("check-usdm", "check_usdm.py")
        assert gate["needsFix"] is True and gate["attempt"] == attempt and gate["retry"] is (attempt < 3), gate
        problems = gate["problems"]
        assert json.loads((run.work / "feedback.json").read_text())["problems"] == problems
    text = "\n".join(problems)
    for expected in ("StudyArm_99", "C25370", "quote not found on protocol page 7",
                     "Encounter(s) without a citation"):
        assert expected in text, (expected, text)
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "failed" and {item["name"] for item in result["files"]} == {"usdm.json", "usdm-citations.json"}, result
    assert "usdm" not in {item["kind"] for item in result["package"]["files"]}, "a failed extraction must not enter the package"


def test_malformed_shape(work: Path) -> None:
    """A wrong shape is a gate problem for the agent, never a crashed step; nullable fields name what is missing."""
    run = Run(work / "malformed")
    protocol = protocol_entry(work, "cdiscpilot01-protocol.pdf", "protocol")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local([protocol])}})
    run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], {protocol["name"]: protocol["localPath"]}))
    target = work / "malformed-usdm"
    shutil.copytree(FIXTURES / "usdm", target)
    document = json.loads((target / "usdm.json").read_text())
    design = document["study"]["versions"][0]["studyDesigns"][0]
    design["objectives"].append("not an objective")
    del design["studyType"]["codeSystem"], design["studyType"]["decode"]
    (target / "usdm.json").write_text(json.dumps(document))
    run.agent(target)
    checked = run.self_check()
    assert checked.returncode == 1 and "Traceback" not in checked.stderr, checked.stderr[-2000:]
    gate = run.step("check-usdm", "check_usdm.py")
    text = "\n".join(gate["problems"])
    assert gate["needsFix"] is True and "objectives/" in text, text
    assert "studyType: 'codeSystem' is a required property" in text and "not of type 'null'" not in text, text


def test_upload_core_round_and_review(work: Path) -> None:
    run = Run(work / "upload")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {}})
    assert resolved["needsUpload"] is True
    uploads = [protocol_entry(work, "LZZT protocol.pdf", None)]
    staged = run.step("stage-inputs", "stage_inputs.py", files=uploads)
    assert [(item["name"], item["kind"]) for item in staged["inputFiles"]] == [("LZZT protocol.pdf", "protocol")], staged

    run.agent(FIXTURES / "usdm")
    assert run.step("check-usdm", "check_usdm.py")["needsFix"] is False
    local = run.core("rejected", "core-run-1", fix_rules=("CORE-000939",), stale_fix="CORE-001013")
    routed = run.step("route-core", "route_core.py")
    assert routed["retry"] is True and routed["round"] == 1, routed
    assert sorted(item["kind"] for item in routed["files"]) == ["core-dispositions-usdm", "core-report-usdm"], routed
    recorded = run.step("record-core", "record_core.py", files=with_local(routed["files"], local))
    assert recorded["rules"] == ["CORE-000939"] and recorded["iteration"] == 1, recorded
    request = json.loads((run.work / "review-feedback.jsonl").read_text().splitlines()[-1])
    assert request["source"] == "core" and "CORE-000939" in request["comment"] and "Use the DDF codelist." in request["comment"], request
    feedback = json.loads((run.work / "core-feedback.json").read_text())
    assert feedback["rules"][0]["instances"][0]["id"] == "Code_9", feedback
    assert (run.work / "attempts.json").is_file() is False, "a CORE round gives fresh attempts"

    run.agent(FIXTURES / "usdm")
    gate = run.step("check-usdm", "check_usdm.py")
    carried = [item for item in gate["package"]["files"] if item["kind"] in ("core-dispositions-usdm", "core-issue-index-usdm")]
    assert sorted(item["kind"] for item in carried) == ["core-dispositions-usdm", "core-issue-index-usdm"], carried
    assert {item["producedBy"]["runId"] for item in carried} == {"core-run-1"}, "dispositions and issue index carry into the next CORE round"
    assert "protocol" in {item["kind"] for item in gate["package"]["files"]}, "the uploaded protocol enters the package"
    run.core("accepted", "core-run-2")
    run.step("prepare-review", "prepare_review.py")
    run.output("review-usdm", {"verdict": "revise", "reviewerComment": "Split the treatment epoch at Week 8."})
    assert run.step("record-review", "record_review.py")["iteration"] == 2
    run.agent(FIXTURES / "usdm")
    run.step("check-usdm", "check_usdm.py")
    run.core("rejected", "core-run-3", fix_rules=("CORE-000939",))
    assert run.step("route-core", "route_core.py")["round"] == 1, "a review round restarts the CORE count"
    run.agent(FIXTURES / "usdm")
    run.step("check-usdm", "check_usdm.py")
    run.core("accepted", "core-run-4")
    run.step("prepare-review", "prepare_review.py")
    run.output("review-usdm", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "digitized", result
    feedback_entry = [item for item in result["files"] if item["kind"] == "review-feedback-digitize-protocol"]
    assert len(feedback_entry) == 1, result["files"]
    protocol = [item for item in result["package"]["files"] if item["kind"] == "protocol"]
    assert protocol and protocol[0]["producedBy"]["step"] == "upload-protocol", protocol


def test_core_exhausted(work: Path) -> None:
    run = Run(work / "exhausted")
    protocol = protocol_entry(work, "cdiscpilot01-protocol.pdf", "protocol")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": {"files": without_local([protocol])}})
    run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], {protocol["name"]: protocol["localPath"]}))
    for round_number in (1, 2, 3):
        run.agent(FIXTURES / "usdm")
        run.step("check-usdm", "check_usdm.py")
        run.core("rejected", f"core-run-{round_number}", fix_rules=("CORE-000939",))
        routed = run.step("route-core", "route_core.py")
        assert routed["retry"] is (round_number < 3) and routed["round"] == round_number, routed
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "failed" and "after 3 round(s)" in result["summary"], result
    assert "usdm" not in {item["kind"] for item in result["package"]["files"]}, result["package"]


def test_compare_against_ground_truth() -> None:
    truth_path = Path(os.environ.get("USDM_TRUTH", Path.home() / "Repo/FULL_WORKFLOW/inputs/usdm.json"))
    if truth_path.is_file() is False:
        print(f"  skipped: no ground truth at {truth_path}")
        return
    truth = json.loads(truth_path.read_text())
    assert all(row.get("missing", 0) == 0 for row in compare(truth, truth).values())
    report = compare(json.loads((FIXTURES / "usdm" / "usdm.json").read_text()), truth)
    for kind in ("objectives", "arms", "inclusion", "exclusion"):
        assert report[kind]["matched"] > 0, (kind, report[kind])
    print("  fixture vs ground truth: " + ", ".join(f"{kind} {row['matched']}/{row['truth']}" for kind, row in report.items()))


def main() -> None:
    if PROTOCOL_PDF.is_file() is False:
        sys.exit(f"Set PROTOCOL_PDF to the CDISCPILOT01 protocol PDF (not found: {PROTOCOL_PDF})")
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for test in (test_digitized, test_gate_failure, test_malformed_shape, test_upload_core_round_and_review, test_core_exhausted):
            test(work)
            print(f"ok {test.__name__}")
    test_compare_against_ground_truth()
    print("ok test_compare_against_ground_truth")


if __name__ == "__main__":
    main()
