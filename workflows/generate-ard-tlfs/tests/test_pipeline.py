"""End-to-end check of the generate-ard-tlfs scripts with real R, fixture programs standing in for the agent.

Simulates what the platform does between steps (per-step /output folder,
input.json = previous output + `steps` + stepParams, downloaded `files` with
localPath, one shared /workspace). Fixtures: a 12-subject ADSL/ADAE, an ARS
ReportingEvent (analysis set, TRTP grouping, label-only data subset), a plan
with one table, one figure and one blocked output, population-counts.json, and
programs that follow the contract (tests/fixtures/programs).

  1. package mode, clean programs -> executed, every displayed number reconciled, big N recounted from ADSL,
     every ARD statistic recomputed, viewer + accuracy.json, outcome generated
  2. a number typed into the display, a bad tag, a missing program -> sent back; three attempts -> failed
  3. a cell showing another arm's mean (a value the ARD holds, in the wrong row) -> rejected
  4. denominators: 5 SAFFL flipped in ADSL after the ARD was made, and a big N off by one in both ARD and
     header -> rejected (reconcile alone passes the second); population-counts.json disagreeing -> a warning only
  5. recompute: an ARD mean shifted by one, displayed consistently -> rejected (reconcile alone passes); an ARD
     written at jsonlite's default 4 decimals -> passes
  5b. a SEX grouping ordered before the treatment grouping -> big N still checked by arm; an analysis grouped by
     SEX alone -> big N not checked; population-counts.json off -> passes with an upstream warning
  6. upload mode, a review round, then 'spec-change' -> outcome upstream_change with the request
  7. the cell checks on their own: missing / miscounted / out-of-range data-ard, an off-by-one digit
     that equals another ARD stat, bounds (<0.001), percentages, header N
  8. the where-clause parser, what the recompute leaves unchecked, rounding tolerance, "Missing" category rows
  9. the real CDISC pilot ADSL (254 subjects) with the demographics program -> passes, when PILOT_ADSL exists

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
INPUT_KINDS = {"tlf-plan.json": "tlf-plan", "analysis-spec.json": "analysis-spec", "reporting-event.json": "ars", "lineage.json": "lineage",
               "population-counts.json": "lineage"}
PILOT_ADSL = Path(os.environ.get("PILOT_ADSL", str(Path.home() / "Repo/experimental-fda-submission-4-podman/submissions-pilot2/datasets/adam/adsl.xpt")))


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
    assert resolved["needsUpload"] is False and len(resolved["files"]) == 7, resolved
    staged = run.step("stage-inputs", "stage_inputs.py", files=with_local(resolved["files"], files))
    assert staged["datasets"] == ["ADAE", "ADSL"] and staged["outputs"] == ["F-14-1", "T-14-2.01"], staged
    return run


def test_generated(work: Path) -> None:
    run = staged_run(work / "generated")
    run.agent(FIXTURES / "programs")
    checked = run.self_check()
    assert checked.returncode == 0 and checked.stdout.startswith("PASS"), checked.stdout + checked.stderr
    assert (run.workspace / "generate-ard-tlfs" / "attempts.json").is_file() is False, "self-check must not use an attempt"

    executed = run.step("execute-programs", "execute_programs.py")
    assert executed["needsFix"] is False and [item["id"] for item in executed["outputs"]] == ["F-14-1", "T-14-2.01"], executed
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["needsFix"] is False and reconciled["checked"] == 12 and reconciled["unmatched"] == 0, reconciled
    assert reconciled["accuracy"]["coverage"] == {"statistics": 12, "recomputed": 12, "mismatches": 0}, reconciled["accuracy"]
    accuracy = json.loads((run.steps_dir / "reconcile" / "accuracy.json").read_text())
    assert accuracy["denominators"]["T-14-2.01"]["expected"] == {"Placebo": 4, "Drug Low": 4, "Drug High": 4, "Total": 12}, accuracy
    assert accuracy["denominators"]["F-14-1"]["status"] == "pass" and accuracy["populationCounts"]["status"] == "compared", accuracy
    page = (run.steps_dir / "reconcile" / "tlf-viewer.html").read_text()
    for expected in ("AN.T-14-2.01", "adsl.R lines [12, 14]", "data:image/png;base64,", "srcdoc=", "@tlf F-14-1", "stat_name",
                     "12 of 12 ARD statistics recomputed from ADaM", "big N recounted from ADSL (SAFFL EQ Y): Placebo 4",
                     "title=&quot;ARD #4: group1_level=Drug Low, variable=AGE, context=continuous, stat_name=mean"):
        assert expected in page, expected

    run.output("review-tlfs", {"verdict": "approve"})
    result = run.step("return-result", "return_result.py")
    assert result["outcome"] == "generated" and result["outputs"] == ["F-14-1", "T-14-2.01"], result
    kinds = {item["name"]: item["kind"] for item in result["package"]["files"]}
    assert kinds["T-14-2.01.json"] == "ard" and kinds["F-14-1.png"] == "tfl" and kinds["tlf-viewer.html"] == "tfl", kinds
    assert kinds["T-14-2.01.R"] == "tfl-program" and kinds["setup.R"] == "tfl-program" and kinds["F-14-1.log"] == "tfl-log", kinds
    assert kinds["adsl.xpt"] == "adam" and kinds["analysis-spec.json"] == "analysis-spec" and kinds["accuracy.json"] == "tfl"


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
    feedback = json.loads((run.workspace / "generate-ard-tlfs" / "feedback.json").read_text())
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
    (work / "header.html").write_text("<table><tr><th></th><th data-ard='7'>Arm 54 mg (N=1)</th><th>Arm (N=2)</th><th>Week 24</th></tr></table>")
    header = reconcile_output("T-1", work / "header.html", work / "cells.json")
    assert header["checked"] == 2 and [item["problem"] for item in header["unmatched"]] == [
        "shows 'Arm (N=2)' without data-ard (the 0-based ARD row of each number)"], header
    (work / "listing.html").write_text("<table><tr><td>01-701-1015</td><td>2014-01-02</td><td data-ard='0'>73.7</td></tr></table>")
    listed = reconcile_output("L-1", work / "listing.html", work / "cells.json", listing=True)["unmatched"]
    assert [item["problem"] for item in listed] == ["shows 73.7, but ARD row 0 (variable=AGE, stat_name=mean) is 73.64"], listed

    from reconcile import linked_display
    linked = linked_display("<html><HEAD></HEAD><table><tr><td>a</td><td data-ard=4>x</td></tr></table></html>",
                            [*ard[:4], {"variable": "AE", "stat_name": "label", "stat": "<\"n\">"}])
    assert "<td data-ard=4 title=\"ARD #4: variable=AE, stat_name=label, stat=&lt;&quot;n&quot;&gt;\">" in linked, linked
    assert "<style>[data-ard]:hover" in linked.split("</HEAD>")[0], linked


def edited_programs(work: Path, name: str, program: str, old: str, new: str) -> Path:
    target = work / name
    shutil.copytree(FIXTURES / "programs", target)
    path = target / program
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new))
    return target


def write_xpt(path: Path, r_expression: str) -> None:
    program = f'data <- haven::read_xpt("{path}"); {r_expression}; haven::write_xpt(data, "{path}", version = 5)'
    completed = subprocess.run(["Rscript", "--vanilla", "-e", program], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_denominators(work: Path) -> None:
    run = staged_run(work / "flipped")
    run.agent(FIXTURES / "programs")
    assert run.step("execute-programs", "execute_programs.py")["needsFix"] is False
    write_xpt(run.workspace / "generate-ard-tlfs" / "inputs" / "adam" / "adsl.xpt", 'data$SAFFL[1:5] <- "N"')
    reconciled = run.step("reconcile", "reconcile.py")
    problems = "\n".join(reconciled["problems"])
    assert reconciled["needsFix"] is True and reconciled["unmatched"] == 0, reconciled
    assert "T-14-2.01: big N for Placebo is 4 in ARD row 9, but ADSL subjects with SAFFL EQ Y and TRT01P = Placebo number 0" in problems, problems
    assert "F-14-1: big N for Drug Low is 4 in ARD row 4, but" in problems and "population-counts.json" not in problems, problems
    assert reconciled["accuracy"]["warnings"][0] == "population-counts.json: SAFFL total is 12, but ADSL has 7 (F-14-1)", reconciled["accuracy"]
    assert (run.workspace / "generate-ard-tlfs" / "tlf-viewer.html").is_file() is False

    run = staged_run(work / "off-by-one")
    run.agent(edited_programs(work, "off-by-one-programs", "T-14-2.01.R", "ard <- rbind(ard, big_n(adsl))",
                              'ard <- rbind(ard, big_n(adsl))\nard$stat[ard$variable == "BIGN" & ard$group1_level == "Placebo"] <- 5'))
    run.step("execute-programs", "execute_programs.py")
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["unmatched"] == 0, "the header shows the ARD's (wrong) N, so the display reconciles"
    assert reconciled["needsFix"] is True and reconciled["problems"] == [
        "T-14-2.01: big N for Placebo is 5 in ARD row 9, but ADSL subjects with SAFFL EQ Y and TRT01P = Placebo number 4 (ARS AS.SAF)"], reconciled
    assert reconciled["accuracy"]["summary"]["denominatorsFailed"] == 1, reconciled


def test_recompute(work: Path) -> None:
    run = staged_run(work / "shifted-mean")
    run.agent(edited_programs(work, "shifted-mean-programs", "T-14-2.01.R", "ard <- rbind(ard, big_n(adsl))",
                              'ard <- rbind(ard, big_n(adsl))\nard$stat[ard$variable == "AGE" & ard$group1_level == "Placebo" & ard$stat_name == "mean"] <- 75.5'))
    run.step("execute-programs", "execute_programs.py")
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["unmatched"] == 0, "the display shows the ARD's (wrong) mean, so the display reconciles"
    assert reconciled["needsFix"] is True and reconciled["problems"] == [
        "T-14-2.01: ARD row 1 (group1_level=Placebo, variable=AGE, context=continuous, stat_name=mean) is 75.5, but recomputing mean "
        "independently from ADSL records of ADSL subjects with SAFFL EQ Y, where TRT01P EQ Placebo gives 74.5 = mean of AGE over its "
        "non-missing values - fix the computation, or declare a narrower slice in the row's filter"], reconciled
    assert reconciled["accuracy"]["coverage"] == {"statistics": 12, "recomputed": 12, "mismatches": 1}, reconciled
    checked = run.self_check()
    assert checked.returncode == 1 and "recomputing mean independently from ADSL" in checked.stdout, "the agent's self-check runs the same gates"

    run = staged_run(work / "rounded-ard")
    run.agent(edited_programs(work, "rounded-ard-programs", "setup.R", "auto_unbox = TRUE, digits = NA)", "auto_unbox = TRUE)"))
    run.step("execute-programs", "execute_programs.py")
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["needsFix"] is False and reconciled["accuracy"]["coverage"] == {"statistics": 12, "recomputed": 12, "mismatches": 0}, reconciled
    rounded = [row["stat"] for row in json.loads((run.steps_dir / "execute-programs" / "ard" / "T-14-2.01.json").read_text())
               if row["stat_name"] == "sd"]
    assert all(len(str(stat).split(".")[-1]) <= 4 for stat in rounded) and any(len(str(stat).split(".")[-1]) == 4 for stat in rounded), rounded


def test_groupings_and_upstream_counts(work: Path) -> None:
    run = staged_run(work / "groupings")
    inputs = run.workspace / "generate-ard-tlfs" / "inputs"
    event = json.loads((inputs / "reporting-event.json").read_text())
    event["analysisGroupings"].insert(0, {"id": "GRP.SEX", "name": "Sex", "dataDriven": True, "groupingDataset": "ADSL", "groupingVariable": "SEX"})
    analyses = {analysis["id"]: analysis for analysis in event["analyses"]}
    analyses["AN.T-14-2.01"]["orderedGroupings"] = [{"order": 1, "groupingId": "GRP.SEX", "resultsByGroup": True},
                                                    {"order": 2, "groupingId": "GRP.TRT", "resultsByGroup": True}]
    analyses["AN.F-14-1"]["orderedGroupings"] = [{"order": 1, "groupingId": "GRP.SEX", "resultsByGroup": True}]
    (inputs / "reporting-event.json").write_text(json.dumps(event))
    counts = json.loads((inputs / "population-counts.json").read_text())
    counts["populations"]["SAFFL"]["total"] = 13
    (inputs / "population-counts.json").write_text(json.dumps(counts))
    run.agent(FIXTURES / "programs")
    run.step("execute-programs", "execute_programs.py")
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["needsFix"] is False and reconciled["accuracy"]["coverage"] == {"statistics": 12, "recomputed": 12, "mismatches": 0}, reconciled
    assert reconciled["accuracy"]["warnings"] == ["population-counts.json: SAFFL total is 13, but ADSL has 12 (T-14-2.01)"], reconciled
    assert "1 upstream warning(s)" in reconciled["summary"], reconciled["summary"]
    accuracy = json.loads((run.steps_dir / "reconcile" / "accuracy.json").read_text())
    table, figure = accuracy["denominators"]["T-14-2.01"], accuracy["denominators"]["F-14-1"]
    assert table["status"] == "pass" and table["grouping"] == "TRT01P" and table["expected"]["Placebo"] == 4, table
    assert figure["status"] == "not checked" and figure["reason"].startswith("none of the ARS analysis groupings is a treatment variable"), figure
    page = (run.steps_dir / "reconcile" / "tlf-viewer.html").read_text()
    assert "Warning (upstream ADaM, not this step's programs): population-counts.json: SAFFL total is 13" in page


def test_accuracy_units(work: Path) -> None:
    sys.path[:0] = [str(ARTIFACTS / "scripts"), str(SHARED)]
    from accuracy import Context, Requests, evaluate_recompute, matches, parse_where, recompute_check

    assert parse_where("PARAMCD IN ('ALT','AST') AND AVISITN IN (0, 24) AND AVAL IS NOT NULL AND DTYPE = ''") == [
        {"variable": "PARAMCD", "comparator": "IN", "values": ["ALT", "AST"]}, {"variable": "AVISITN", "comparator": "IN", "values": [0, 24]},
        {"variable": "AVAL", "comparator": "NOTNULL", "values": []}, {"variable": "DTYPE", "comparator": "EQ", "values": [""]}]
    assert parse_where("AEBODSYS = 'BLOOD AND LYMPHATIC SYSTEM DISORDERS'") == [
        {"variable": "AEBODSYS", "comparator": "EQ", "values": ["BLOOD AND LYMPHATIC SYSTEM DISORDERS"]}]
    assert parse_where("(all concomitant-medication records)") == [] and parse_where("SEX = 'F' OR AGE > 65") is None
    assert parse_where("substr(PARAMCD, 1, 2) = 'AL'") is None

    event = json.loads((FIXTURES / "reporting-event.json").read_text())
    event["methods"].append({"id": "MTH.ANCOVA", "name": "ANCOVA of change from baseline", "operations": []})
    event["analyses"].append({**event["analyses"][0], "id": "AN.MODEL", "methodId": "MTH.ANCOVA"})
    columns = {"ADSL": ["USUBJID", "TRT01P", "SAFFL", "AGE"]}
    rows = [{"variable": "AGE", "stat_name": "mean", "stat": 1}, {"variable": "AGE", "stat_name": "lsmean", "stat": 1},
            {"variable": "BIGN", "stat_name": "N", "stat": 4}, {"variable": "AGE", "stat_name": "label", "stat": "Mean"}]
    model = recompute_check("T-1", Context(event, "AN.MODEL", columns), rows, Requests(), [])
    assert model["statistics"] == 2 and model["notChecked"] == {"method ANCOVA of change from baseline is not a simple summary": 2}, model
    plans = []
    simple = recompute_check("T-1", Context(event, "AN.T-14-2.01", columns), [*rows, {"variable": "TEAE", "stat_name": "n", "stat": 3},
                                                                             {"variable": "AGE", "stat_name": "mean", "stat": 1, "filter": "AGE >"}],
                             Requests(), plans)
    assert len(plans) == 1 and simple["notChecked"] == {"statistic lsmean": 1, "variable TEAE is not an ADaM column": 1}, simple
    assert simple["problems"] == ["T-1: ARD row 5: filter 'AGE >' is not a where-clause of AND-ed comparisons (e.g. PARAMCD = 'ALT' AND AVISITN = 24)"]

    assert matches(0.3386, 86 / 254) is True and matches(33.86, 8600 / 254) is True and matches(0.34, 86 / 254) is True
    assert matches(74, 74.4) is False and matches(0.3387, 86 / 254) is False and matches(75.5, 74.5) is False

    adam = work / "missing-adam"
    shutil.copytree(FIXTURES / "adam", adam)
    write_xpt(adam / "adsl.xpt", 'data$RACE <- ifelse(data$USUBJID %in% c("01-001", "01-002", "01-005"), "", "WHITE")')
    columns = {"ADSL": ["USUBJID", "TRT01P", "SAFFL", "AGE", "RACE"]}
    context = Context(event, "AN.T-14-2.01", columns)

    def race(level: str, arm: str, stat_name: str, stat: float) -> dict:
        return {"group1": "TRT01P", "group1_level": arm, "variable": "RACE", "variable_level": level, "stat_name": stat_name, "stat": stat}

    rows = [race("Missing", "Placebo", "n", 2), race("MISSING", "Placebo", "p", 0.5), race("", "Drug Low", "n", 1),
            race("missing", "Drug Low", "pct", 25), race("WHITE", "Placebo", "n", 2), race("Missing", "Drug High", "n", 1)]
    requests, plans = Requests(), []
    report = recompute_check("T-1", context, rows, requests, plans)
    requests.run(adam)
    evaluate_recompute("T-1", report, plans, requests, context)
    assert report["recomputed"] == 6 and [item["row"] for item in report["mismatches"]] == [5], report
    assert "is 1, but recomputing n independently from ADSL records of ADSL subjects with SAFFL EQ Y, where TRT01P EQ Drug High AND RACE ISNULL " \
           "gives 0 = subjects with RACE missing" in report["problems"][0], report["problems"]


def test_pilot(work: Path) -> None:
    if PILOT_ADSL.is_file() is False:
        print(f"skip test_pilot: no {PILOT_ADSL}")
        return
    inputs = work / "pilot-inputs"
    inputs.mkdir()
    shutil.copyfile(PILOT_ADSL, inputs / "adsl.xpt")
    for name in ("tlf-plan.json", "reporting-event.json"):
        shutil.copyfile(FIXTURES / name, inputs / name)
    spec = [item for item in json.loads((FIXTURES / "analysis-spec.json").read_text()) if item["table_id"] == "T-14-2.01"]
    (inputs / "analysis-spec.json").write_text(json.dumps(spec))
    (inputs / "population-counts.json").write_text(json.dumps({"armVariable": "TRT01A", "populations": {
        "SAFFL": {"total": 254, "byArm": {"Placebo": 86, "Xanomeline Low Dose": 84, "Xanomeline High Dose": 84}}}}))
    files = [entry(inputs / "adsl.xpt", "adam")] + [entry(inputs / name, kind) for name, kind in INPUT_KINDS.items() if name != "lineage.json"]
    run = Run(work / "pilot")
    run.step("resolve-inputs", "resolve_inputs.py", {"package": {}})
    run.step("stage-inputs", "stage_inputs.py", files=files)
    programs = work / "pilot-programs"
    shutil.copytree(FIXTURES / "programs", programs)
    (programs / "F-14-1.R").unlink()
    run.agent(programs)
    assert run.step("execute-programs", "execute_programs.py")["needsFix"] is False
    reconciled = run.step("reconcile", "reconcile.py")
    assert reconciled["needsFix"] is False and reconciled["accuracy"]["coverage"] == {"statistics": 9, "recomputed": 9, "mismatches": 0}, reconciled
    accuracy = json.loads((run.steps_dir / "reconcile" / "accuracy.json").read_text())
    assert accuracy["denominators"]["T-14-2.01"]["expected"]["Total"] == 254 and accuracy["populationCounts"]["status"] == "compared", accuracy
    print(f"    pilot: {reconciled['summary']}")


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
    assert (run.workspace / "generate-ard-tlfs" / "attempts.json").is_file() is False, "a review round gets fresh attempts"
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
        for test in (test_generated, test_failures, test_wrong_row, test_denominators, test_recompute, test_groupings_and_upstream_counts,
                     test_upload_review_and_upstream, test_cell_checks, test_accuracy_units, test_pilot):
            test(work)
            print(f"ok  {test.__name__}")


if __name__ == "__main__":
    main()
