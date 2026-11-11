"""End-to-end check of the cdisc-core-validation scripts against a real CORE binary.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath) and runs resolve -> run-core -> build-report -> decide.

Needs a CORE release unpacked locally and the pilot datasets:
  CORE_HOME=/path/to/core  SDTM_DIR=/path/to/sdtm  ADAM_DIR=/path/to/adam  python3 tests/test_pipeline.py
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


class Run:
    """One simulated workflow run: a worktree, its step outputs and variables."""

    def __init__(self, root: Path, scripts: Path):
        self.root = root
        self.scripts = scripts
        self.steps_dir = root / ".mediforce" / "output"
        self.variables: dict[str, dict] = {}
        self.previous: dict = {}

    def step(self, step_id: str, script: str, params: dict | None = None, files: list[dict] | None = None) -> dict:
        output_dir = self.steps_dir / step_id
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True)
        step_input = {**self.previous, "steps": self.variables, **(params or {})}
        if files is not None:
            step_input["files"] = files
        (output_dir / "input.json").write_text(json.dumps(step_input), encoding="utf-8")
        environment = {**os.environ, "MEDIFORCE_OUTPUT_DIR": str(output_dir), "MEDIFORCE_STEP_OUTPUTS_DIR": str(self.steps_dir),
                       "RUN_ID": "run-test", "STEP_ID": step_id, "CORE_LOCAL_RULES": str(ARTIFACTS / "rules"),
                       "CORE_WORK_DIR": str(self.root / "work" / step_id)}
        completed = subprocess.run([sys.executable, str(self.scripts / script)], env=environment, capture_output=True, text=True)
        result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
        if completed.returncode != 0:
            raise AssertionError(f"{step_id} failed: {result.get('error')}\n{completed.stderr[-2000:]}")
        self.variables[step_id] = result
        self.previous = result
        return result

    def human(self, step_id: str, output: dict) -> None:
        self.variables[step_id] = output
        self.previous = output


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_uploads(paths: list[Path], kind: str | None = None) -> list[dict]:
    entries = []
    for path in paths:
        entry = {"name": path.name, "downloadUrl": f"/api/attachments/{path.name}/blob", "localPath": str(path), "sha256": sha(path)}
        if kind:
            entry["kind"] = kind
        entries.append(entry)
    return entries


def localize(files: list[dict], run_root: Path, sources: dict[str, Path]) -> list[dict]:
    """What the runtime does with a package's files: download each to a local path."""
    localized = []
    for entry in files:
        if entry["downloadUrl"].startswith("/api/runs/"):
            relative = entry["downloadUrl"].split("/files/", 1)[1]
            local = run_root / relative
        else:
            local = sources[entry["name"]]
        localized.append({**entry, "localPath": str(local)})
    return localized


def scripts_dir(root: Path) -> Path:
    target = root / "artifacts-scripts"
    shutil.copytree(ARTIFACTS / "scripts", target)
    for helper in SHARED.glob("*.py"):
        shutil.copyfile(helper, target / helper.name)
    return target


def dispositions_for(options: list[dict], choice: str, justification: str = "") -> dict:
    return {"rows": [{"itemId": option["id"], "values": {"disposition": choice, "justification": justification}} for option in options]}


def test_sdtm_upload_reject_then_accept(work: Path) -> None:
    sdtm_dir = Path(os.environ["SDTM_DIR"])
    uploads = as_uploads(sorted(sdtm_dir.glob("*.xpt")) + [sdtm_dir / "define.xml"])
    run = Run(work / "sdtm", scripts_dir(work / "sdtm"))
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": "", "standard": "sdtmig", "version": "", "ct": "", "onReject": ""})
    assert resolved["needsUpload"] is True and resolved["config"]["onReject"] == "reupload", resolved
    run.human("upload-datasets", {"files": uploads})
    core = run.step("run-core", "run_core.py", files=uploads)
    assert core["issueCount"] > 0 and core["datasets"], core["summary"]
    report = run.step("build-report", "build_report.py")
    assert report["needsReview"] is True and report["options"], report["summary"]
    html = (run.steps_dir / "build-report" / "core-report.html").read_text(encoding="utf-8")
    assert "__DATA__" not in html and "CDISC CORE" in html
    run.human("review-dispositions", dispositions_for(report["options"], "fix"))
    decided = run.step("decide", "decide.py")
    assert decided["outcome"] == "rejected" and decided["onReject"] == "reupload", decided["summary"]
    kinds = sorted({entry["kind"] for entry in decided["package"]["files"]})
    assert "sdtm" in kinds and "sdtm-define" in kinds and "core-report-sdtmig" in kinds, kinds
    print("  sdtm reject:", decided["summary"])

    run.human("review-dispositions", dispositions_for(report["options"], "justified", "Known in the pilot data."))
    accepted = run.step("decide", "decide.py")
    assert accepted["outcome"] == "accepted", accepted["summary"]
    print("  sdtm accept:", accepted["summary"])


def write_lineage(folder: Path) -> list[Path]:
    program = folder / "adsl.R"
    program.write_text("\n".join([
        "library(admiral)",
        "# @derive ADSL.TRTSDT origin=Derived spec=ADSL.TRTSDT src=EX.EXSTDTC",
        "adsl <- adsl %>%",
        "  derive_vars_merged(dataset_add = ex_ext, new_vars = exprs(TRTSDTM = EXSTDTM),",
        "                     order = exprs(EXSTDTM, EXSEQ), mode = 'first', by_vars = exprs(STUDYID, USUBJID)) %>%",
        "  derive_vars_dtm_to_dt(exprs(TRTSDTM))",
        "# @derive ADSL.SAFFL origin=Derived spec=ADSL.SAFFL src=EX.EXDOSE",
        "adsl <- derive_var_merged_exist_flag(adsl, dataset_add = ex, by_vars = exprs(STUDYID, USUBJID),",
        "                                     new_var = SAFFL, condition = EXDOSE > 0)",
    ]) + "\n", encoding="utf-8")
    lineage = folder / "lineage.json"
    lineage.write_text(json.dumps({
        "variables": [
            {"dataset": "ADSL", "variable": "TRTSDT", "origin": "Derived", "program": "adsl.R", "lines": [2, 6], "spec": "ADSL.TRTSDT", "sources": ["EX.EXSTDTC"]},
            {"dataset": "ADSL", "variable": "SAFFL", "origin": "Derived", "program": "adsl.R", "lines": [7, 9], "spec": "ADSL.SAFFL", "sources": ["EX.EXDOSE"]},
            {"dataset": "ADLBC", "variable": "PARAMCD", "origin": "Derived", "program": "adlbc.R", "lines": [1, 3], "spec": "ADLBC.PARAMCD", "sources": ["LB.LBTESTCD"]},
        ],
        "consumers": {"ADSL.SAFFL": ["T-14.1.1", "T-14.3.1"], "ADSL.TRTSDT": ["T-14.3.1"]},
    }), encoding="utf-8")
    return [lineage, program]


def test_adam_package_trace_and_diff(work: Path) -> None:
    adam_dir = Path(os.environ["ADAM_DIR"])
    import pyreadstat

    seeded = work / "adam-seeded"
    seeded.mkdir(parents=True)
    adsl, meta = pyreadstat.read_xport(str(adam_dir / "adsl.xpt"))
    adsl.loc[1, "SAFFL"] = "X"
    adsl.loc[3, "TRTSDT"] = float("nan")
    adsl.loc[3, "SAFFL"] = "Y"
    pyreadstat.write_xport(adsl, str(seeded / "adsl.xpt"), table_name="ADSL", column_labels=meta.column_labels, file_format_version=5)
    trace_files = write_lineage(seeded)

    sources = {path.name: path for path in [seeded / "adsl.xpt", *trace_files]}
    package = {"study": {"id": "CDISCPILOT01"}, "profile": {"adamig": "1-3"}, "files": [
        {"name": "adsl.xpt", "downloadUrl": "/api/attachments/adsl/blob", "kind": "adam", "sha256": sha(seeded / "adsl.xpt")},
        {"name": "lineage.json", "downloadUrl": "/api/attachments/lineage/blob", "kind": "lineage", "sha256": sha(trace_files[0])},
        {"name": "adsl.R", "downloadUrl": "/api/attachments/adslr/blob", "kind": "adam-program", "sha256": sha(trace_files[1])},
    ]}
    run = Run(work / "adam", scripts_dir(work / "adam"))
    resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": package, "standard": "adamig", "version": "", "ct": "", "onReject": ""})
    assert resolved["needsUpload"] is False and resolved["config"]["onReject"] == "return" and resolved["config"]["version"] == "1-3", resolved
    core = run.step("run-core", "run_core.py", files=localize(resolved["files"], run.root, sources))
    assert core["ruleStatusCounts"].get("ISSUE REPORTED", 0) >= 2, core
    report = run.step("build-report", "build_report.py")
    assert report["lineage"] is True
    html = (run.steps_dir / "build-report" / "core-report.html").read_text(encoding="utf-8")
    data = json.loads(html.split("const DATA = ", 1)[1].split(";\nconst esc", 1)[0].replace("<\\/", "</"))
    trtsdt = next(group for group in data["groups"] if group["coreId"] == "MF-ADAM-004")
    derivation = next(item for item in trtsdt["trace"]["derivations"] if item["variable"] == "ADSL.TRTSDT")
    assert derivation["program"] == "adsl.R" and derivation["snippet"]["highlight"] == [2, 6] and "T-14.3.1" in derivation["usedBy"], derivation
    run.human("review-dispositions", dispositions_for(report["options"], "fix"))
    decided = run.step("decide", "decide.py")
    assert decided["outcome"] == "rejected" and decided["onReject"] == "return", decided["summary"]
    print("  adam pass 1:", decided["summary"])

    # The parent regenerates ADSL with SAFFL fixed and validates the returned package again.
    fixed = work / "adam-fixed"
    fixed.mkdir()
    adsl.loc[1, "SAFFL"] = "Y"
    pyreadstat.write_xport(adsl, str(fixed / "adsl.xpt"), table_name="ADSL", column_labels=meta.column_labels, file_format_version=5)
    second_package = dict(decided["package"])
    second_package["files"] = [entry if entry["name"] != "adsl.xpt" else {**entry, "sha256": sha(fixed / "adsl.xpt")} for entry in second_package["files"]]
    sources["adsl.xpt"] = fixed / "adsl.xpt"
    second = Run(work / "adam2", scripts_dir(work / "adam2"))
    previous_run_files = {entry["name"]: run.root / entry["downloadUrl"].split("/files/", 1)[1] for entry in second_package["files"] if entry["downloadUrl"].startswith("/api/runs/")}
    resolved = second.step("resolve-inputs", "resolve_inputs.py", {"package": second_package, "standard": "adamig", "version": "", "ct": "", "onReject": ""})
    localized = [{**entry, "localPath": str(previous_run_files.get(entry["name"]) or sources[entry["name"]])} for entry in resolved["files"]]
    second.step("run-core", "run_core.py", files=localized)
    report = second.step("build-report", "build_report.py")
    assert report["counts"]["fixed"] == 1 and report["counts"]["new"] == 0, report["counts"]
    previously = [option["previously"] for option in report["options"] if option["rule"] == "MF-ADAM-004"]
    assert previously and previously[0].startswith("fix"), report["options"]
    print("  adam pass 2:", report["summary"])


def main() -> None:
    for name in ("CORE_HOME", "SDTM_DIR", "ADAM_DIR"):
        if not os.environ.get(name):
            raise SystemExit(f"Set {name} (see the module docstring).")
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for test in (test_sdtm_upload_reject_then_accept, test_adam_package_trace_and_diff):
            print(test.__name__)
            test(work)
    print("all passed")


if __name__ == "__main__":
    main()
