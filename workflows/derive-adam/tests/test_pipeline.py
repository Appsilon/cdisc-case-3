"""End-to-end check of the derive-adam scripts with real R and real SDTM.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath, one shared /workspace) and stands in for the agent with the fixture
programs in tests/fixtures/programs:

  1. package mode, clean programs  -> outcome derived; lineage, define, package kinds
  2. an untagged column and an untagged extra column -> check-lineage sends it back (retry),
     then, attempts used up -> outcome failed
  3. fix loop: package carrying programs + CORE dispositions -> fixMode, findings staged
  4. population gate (seeded defects): the real pilot ADaM passes; 5 flipped SAFFL, a dropped
     ADSL subject, 3 swapped TRT01P and an ADSL from the 18-subject synthetic SDTM fail;
     Unplanned Treatment / ACTARM != ARM pass (noted); an unreadable ADaM .xpt is the agent's
     problem, an unreadable DM a StepFailure; and a flipped SAFFL in the programs goes back to the agent

Needs R with haven, jsonlite, dplyr, admiral. SDTM_DIR defaults to the real CDISC pilot SDTM;
PILOT_ADAM_DIR (the pilot's ADaM) and SYNTHETIC_SDTM_DIR (the 18-subject set) default to the
local checkouts below, and their seeded-defect checks are skipped when the folder is missing:
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
import xml.etree.ElementTree as ElementTree
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parent / "artifacts"
SHARED = HERE.parent.parent / "shared"
FIXTURES = HERE / "fixtures"
REPO = Path.home() / "Repo"
DEFAULT_SDTM_DIR = REPO / "protocol-to-tfl" / "test-docs" / "cdiscpilot01" / "sdtm"
DEFAULT_PILOT_ADAM_DIR = REPO / "experimental-fda-submission-4-podman" / "submissions-pilot2" / "datasets" / "adam"
DEFAULT_SYNTHETIC_SDTM_DIR = REPO / "FULL_WORKFLOW" / "inputs" / "sdtm"


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
    assert (run.workspace / "derive-adam" / "attempts.json").is_file() is False, "self-check must not use an attempt"

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

    assert lineage_gate["notes"] == [], lineage_gate["notes"]
    populations = json.loads((run.steps_dir / "check-lineage" / "population-counts.json").read_text(encoding="utf-8"))
    assert populations == lineage_gate["populations"], "population-counts.json and the step output must agree"
    assert populations["armVariable"] == "TRT01P" and populations["datasets"]["ADSL"]["records"] == 306, populations
    pilot_arms = {"Placebo": 86, "Xanomeline High Dose": 84, "Xanomeline Low Dose": 84}
    assert populations["populations"]["SAFFL"] == {"total": 254, "byArm": pilot_arms}, populations["populations"]
    assert populations["populations"]["ITTFL"] == {"total": 254, "byArm": pilot_arms}, populations["populations"]

    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "derived", result["summary"]
    assert {item["name"] for item in result["package"]["files"] if item["kind"] == "lineage"} == {"lineage.json", "population-counts.json"}
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
        feedback = json.loads((run.workspace / "derive-adam" / "feedback.json").read_text(encoding="utf-8"))
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
             entry(lineage, "lineage"), {**entry(lineage, "lineage"), "name": "population-counts.json"},
             entry(dispositions, "core-dispositions-adamig"), entry(report, "core-report-adamig"),
             {**entry(report, "core-report-adamig"), "name": "core-report.html"}]
    package = package_for(sdtm_dir, FIXTURES / "adam-spec.json", extra)
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": without_local(package)})
    names = [item["name"] for item in resolved["files"]]
    assert "core-report.json" in names and "core-report.html" not in names, names
    assert "population-counts.json" not in names, names
    local = {item["name"]: item["localPath"] for item in package["files"]}
    staged = run.step("stage-inputs", "stage_inputs.py", files=[{**item, "localPath": local[item["name"]]} for item in resolved["files"]])
    assert staged["fixMode"] is True and staged["findings"] == 1, staged
    findings = json.loads((run.workspace / "derive-adam" / "inputs" / "core-findings.json").read_text(encoding="utf-8"))["findings"]
    assert findings[0]["rule"] == "MF-ADAM-004" and findings[0]["examples"][0]["USUBJID"] == "CDISC003", findings
    assert (run.workspace / "programs" / "adsl.R").is_file() and (run.workspace / "derive-adam" / "inputs" / "previous-lineage.json").is_file()
    print("  fix loop:", staged["summary"])

    # Dispositions without programs (e.g. after an SDTM re-upload dropped them): not a fix loop.
    orphan = Run(work / "orphan")
    package = package_for(sdtm_dir, FIXTURES / "adam-spec.json", [entry(dispositions, "core-dispositions-adamig"), entry(report, "core-report-adamig")])
    resolved = orphan.step("resolve-inputs", "resolve_inputs.py", {"package": without_local(package)})
    local = {item["name"]: item["localPath"] for item in package["files"]}
    staged = orphan.step("stage-inputs", "stage_inputs.py", files=[{**item, "localPath": local[item["name"]]} for item in resolved["files"]])
    findings = json.loads((orphan.workspace / "derive-adam" / "inputs" / "core-findings.json").read_text(encoding="utf-8"))["findings"]
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


SEED_R = r"""
arguments <- commandArgs(TRUE)
mode <- arguments[1]; source_dir <- arguments[2]; target_dir <- arguments[3]
library(dplyr, warn.conflicts = FALSE)
if (mode == "synthetic") {
  dm <- haven::read_xpt(file.path(source_dir, "dm.xpt"))
  ex <- haven::read_xpt(file.path(source_dir, "ex.xpt"))
  adsl <- dm %>% transmute(STUDYID, USUBJID, TRT01P = ARM, TRT01A = ACTARM,
                           ITTFL = if_else(ARM == "", "N", "Y"), SAFFL = if_else(USUBJID %in% ex$USUBJID, "Y", "N"))
} else {
  adsl <- haven::read_xpt(file.path(source_dir, "adsl.xpt"))
  if (mode == "flip-saffl") adsl$SAFFL[1:5] <- "N"
  if (mode == "drop-subject") adsl <- adsl[-1, ]
  if (mode == "swap-trt01p") adsl$TRT01P[which(adsl$TRT01P == "Placebo")[1:3]] <- "Xanomeline High Dose"
}
haven::write_xpt(adsl, file.path(target_dir, "adsl.xpt"), version = 5, name = "ADSL")
"""


def seeded_adam(work: Path, mode: str, source_dir: Path, pilot_adam: Path) -> Path:
    """The pilot ADaM folder with ADSL replaced by a seeded defect."""
    target = work / f"adam-{mode}"
    target.mkdir(parents=True)
    for dataset in pilot_adam.glob("*.xpt"):
        if dataset.name.lower() != "adsl.xpt":
            (target / dataset.name.lower()).symlink_to(dataset)
    program = work / "seed.R"
    program.write_text(SEED_R, encoding="utf-8")
    subprocess.run(["Rscript", "--vanilla", str(program), mode, str(source_dir), str(target)], check=True, capture_output=True, text=True)
    return target


def populations_module():
    sys.path[:0] = [str(ARTIFACTS / "scripts"), str(SHARED)]
    import populations
    return populations


def population_check(sdtm_dir: Path, adam_dir: Path) -> tuple[list[str], list[str], dict]:
    return populations_module().gate_populations(sdtm_dir, adam_dir)


def population_check_data(data: dict) -> tuple[list[str], list[str], dict]:
    return populations_module().check(data)


def test_population_gate(work: Path, sdtm_dir: Path) -> None:
    pilot_adam = Path(os.environ.get("PILOT_ADAM_DIR", str(DEFAULT_PILOT_ADAM_DIR)))
    synthetic_sdtm = Path(os.environ.get("SYNTHETIC_SDTM_DIR", str(DEFAULT_SYNTHETIC_SDTM_DIR)))
    if (pilot_adam / "adsl.xpt").is_file() is False:
        print(f"  SKIPPED: no pilot ADaM at {pilot_adam}")
    else:
        problems, notes, counts = population_check(sdtm_dir, pilot_adam)
        assert problems == [], problems
        assert len(notes) == 1 and "TRT01A follows DM.ARM" in notes[0] and "12 subject(s)" in notes[0], notes
        arms = {"Placebo": 86, "Xanomeline High Dose": 84, "Xanomeline Low Dose": 84}
        assert counts["armVariable"] == "TRT01A" and counts["datasets"]["ADSL"] == {"records": 254}, counts
        assert counts["populations"]["SAFFL"] == {"total": 254, "byArm": arms} and counts["populations"]["ITTFL"]["total"] == 254, counts
        assert counts["populations"]["EFFFL"]["byArm"] == {"Placebo": 79, "Xanomeline High Dose": 74, "Xanomeline Low Dose": 81}, counts
        print("  pilot ADaM vs pilot SDTM: PASS;", notes[0][:90])

        problems, _, counts = population_check(sdtm_dir, seeded_adam(work, "flip-saffl", pilot_adam, pilot_adam))
        assert len(problems) == 1 and problems[0].startswith("ADSL.SAFFL='Y' for 249 subject(s), but 254 are exposed"), problems
        assert counts["populations"]["SAFFL"]["total"] == 249, counts
        print("  5 SAFFL flipped: FAIL as expected:", problems[0][:150])

        problems, _, _ = population_check(sdtm_dir, seeded_adam(work, "drop-subject", pilot_adam, pilot_adam))
        joined = "\n".join(problems)
        assert "Randomised in DM but missing from ADSL: 01-701-1015" in joined, joined
        assert "ADADAS has 1 USUBJID(s) that are not in ADSL: 01-701-1015" in joined, joined
        print(f"  ADSL subject dropped: FAIL as expected ({len(problems)} problems)")

        problems, _, _ = population_check(sdtm_dir, seeded_adam(work, "swap-trt01p", pilot_adam, pilot_adam))
        assert len(problems) == 2 and problems[0].startswith("DM.ARM 'Placebo' maps to more than one ADSL.TRT01P"), problems
        assert problems[1].startswith("ADSL.TRT01P 'Xanomeline High Dose' maps to more than one DM.ARM"), problems
        print("  3 TRT01P swapped: FAIL as expected:", problems[0][:120])

        if (synthetic_sdtm / "dm.xpt").is_file() is False:
            print(f"  SKIPPED: no synthetic SDTM at {synthetic_sdtm}")
        else:
            problems, _, _ = population_check(sdtm_dir, seeded_adam(work, "synthetic", synthetic_sdtm, pilot_adam))
            joined = "\n".join(problems)
            assert "ADSL holds 18 subject(s); DM has 306, 254 randomised" in joined and "Not in DM: CDISC001" in joined, joined
            assert "ADADAS has 254 USUBJID(s) that are not in ADSL" in joined, joined
            print(f"  synthetic 18-subject ADSL vs real DM: FAIL as expected ({len(problems)} problems):", problems[0][:120])

    problems, _, _ = population_check_data({
        "sdtm": {"DM": {"USUBJID": ["S1", "S2", "S3", "S4"], "ARMCD": ["PBO", "Scrnfail", "NOTASSGN", "PBO"],
                        "ARM": ["Placebo", "Screen Failure", "Not Assigned", "Placebo"],
                        "ACTARMCD": ["PBO", "Scrnfail", "NOTASSGN", "NOTTRT"], "ACTARM": ["Placebo", "Screen Failure", "Not Assigned", "Not Treated"]},
                 "EX": {"USUBJID": ["S1"], "EXSTDTC": ["2020-01-01"]}},
        "adam": {"ADSL": {"records": 4, "columns": {"USUBJID": ["S1", "S2", "S3", "S4"], "TRT01P": ["Placebo", "", "", "Placebo"],
                                                    "TRT01A": ["Placebo", "", "", ""], "SAFFL": ["Y", "N", "N", "N"], "ITTFL": ["Y", "N", "N", "Y"]}}},
    })
    assert problems == [], problems
    print("  blank TRT01P/TRT01A for screen failure, not assigned and not treated: PASS")

    problems, notes, _ = population_check_data({
        "sdtm": {"DM": {"USUBJID": ["S1", "S2", "S3", "S4"], "ARMCD": ["PBO", "SCRNFAIL", "PBO", "PBO"],
                        "ARM": ["Placebo", "Screen Failure", "Placebo", "Placebo"],
                        "ACTARMCD": ["PBO", "SCRNFAIL", "UNPLAN", "DRG"], "ACTARM": ["Placebo", "Screen Failure", "Unplanned Treatment", "Drug"]},
                 "EX": {"USUBJID": ["S1", "S4"], "EXSTDTC": ["2020-01-01", "2020-01-02"]}},
        "adam": {"ADSL": {"records": 3, "columns": {"USUBJID": ["S1", "S3", "S4"], "TRT01P": ["Placebo", "Placebo", "Placebo"],
                                                    "TRT01A": ["Placebo", "", "Drug"], "SAFFL": ["Y", "N", "Y"], "ITTFL": ["Y", "Y", "Y"]}}},
    })
    assert problems == [], problems
    assert notes == ["ADSL.TRT01A follows DM.ACTARM: 1 treated subject(s) have ACTARM != ARM (S4), so their TRT01A differs from TRT01P."], notes
    print("  upper-case SCRNFAIL, Unplanned Treatment, ACTARM != ARM noted: PASS")

    broken_adam = work / "broken-adam"
    broken_adam.mkdir()
    (broken_adam / "adsl.xpt").write_bytes(b"not an xpt file")
    problems, _, counts = population_check(sdtm_dir, broken_adam)
    assert len(problems) == 1 and problems[0].startswith("adsl.xpt cannot be read with haven::read_xpt:") and counts["populations"] == {}, problems
    broken_sdtm = work / "broken-sdtm"
    broken_sdtm.mkdir()
    (broken_sdtm / "dm.xpt").write_bytes(b"not an xpt file")
    try:
        population_check(broken_sdtm, broken_adam)
        raise AssertionError("an unreadable DM must fail the step")
    except populations_module().StepFailure as failure:
        assert "Could not read the staged DM / EX" in str(failure), failure
    print("  unreadable ADaM .xpt -> agent problem; unreadable DM -> StepFailure: PASS")

    run = Run(work / "population")
    package = package_for(sdtm_dir, FIXTURES / "adam-spec.json")
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": without_local(package)})
    local = {item["name"]: item["localPath"] for item in package["files"]}
    run.step("stage-inputs", "stage_inputs.py", files=[{**item, "localPath": local[item["name"]]} for item in resolved["files"]])
    flipped = work / "flipped-programs"
    shutil.copytree(FIXTURES / "programs", flipped)
    adsl = flipped / "adsl.R"
    adsl.write_text(adsl.read_text(encoding="utf-8").replace(
        'if (sum(adsl$SAFFL == "Y") == 0)',
        'adsl$SAFFL[which(adsl$SAFFL == "Y")[1:5]] <- "N"\n\nif (sum(adsl$SAFFL == "Y") == 0)'), encoding="utf-8")
    run.agent(flipped)
    executed, lineage_gate = run_gates(run)
    assert executed["needsFix"] is False, executed["problems"]
    assert lineage_gate["needsFix"] is True and lineage_gate["retry"] is True, lineage_gate
    assert len(lineage_gate["problems"]) == 1 and "ADSL.SAFFL='Y' for 249 subject(s), but 254 are exposed" in lineage_gate["problems"][0], lineage_gate
    feedback = json.loads((run.workspace / "derive-adam" / "feedback.json").read_text(encoding="utf-8"))
    assert feedback["step"] == "check-lineage" and feedback["problems"] == lineage_gate["problems"], feedback
    print("  flipped SAFFL in the programs: back to the agent:", lineage_gate["problems"][0][:120])


def r_libraries() -> str:
    """Programs run with Rscript --vanilla, which skips ~/.Renviron; hand the local library paths over explicitly."""
    completed = subprocess.run(["Rscript", "-e", "cat(.libPaths(), sep = ':')"], capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def main() -> None:
    os.environ["R_LIBS"] = r_libraries()
    sdtm = os.environ.get("SDTM_DIR", str(DEFAULT_SDTM_DIR))
    if (Path(sdtm) / "dm.xpt").is_file() is False:
        raise SystemExit(f"No dm.xpt in {sdtm}: set SDTM_DIR to the CDISC pilot SDTM (see the module docstring).")
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for test in (test_upload_mode, test_fix_loop_staging, test_derived, test_gate_retry_then_failed, test_population_gate):
            print(test.__name__)
            test(work, Path(sdtm))
    print("all passed")


if __name__ == "__main__":
    main()
