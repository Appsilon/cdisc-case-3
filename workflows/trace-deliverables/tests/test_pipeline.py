"""trace-deliverables on a small synthetic study package: the model links every chain, gaps are reported, the steps run.

  python3 tests/test_pipeline.py          (R haven, when installed, also covers profile_adam.R)
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
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "artifacts" / "scripts"
SHARED = HERE.parent.parent / "shared"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SHARED))

from build_explorer import build  # noqa: E402
from tracemodel import build_model  # noqa: E402

ADSL_R = """source("setup.R")
dm <- read_sdtm("dm")
ex <- read_sdtm("ex")

exposed <- ex %>% filter(!is.na(EXSTDTC)) %>% distinct(USUBJID)

# @derive ADSL.USUBJID origin=Predecessor src=DM.*
adsl <- dm %>% transmute(USUBJID)

# @derive ADSL.TRTP origin=Derived src=DM.ARM method="Planned treatment = DM.ARM"
adsl$TRTP <- dm$ARM

# @derive ADSL.SAFFL origin=Derived src=EX.EXSTDTC method="Y if any EX record has a start date"
adsl$SAFFL <- ifelse(adsl$USUBJID %in% exposed$USUBJID, "Y", "N")
"""
ADAE_R = """source("setup.R")
adsl <- read_adam("adsl")
ae <- read_sdtm("ae")

# @derive ADAE.USUBJID,ADAE.AEDECOD origin=Predecessor src=AE.*
# @derive ADAE.TRTP origin=Predecessor src=ADSL.TRTP
adae <- ae %>% inner_join(adsl, by = "USUBJID") %>% select(USUBJID, AEDECOD, TRTP)

# @derive ADAE.TRTEMFL origin=Derived src=ADSL.NOTAVAR method="seeded broken source"
adae$TRTEMFL <- "Y"
"""
T1_R = """# @tlf T-1 analysis=AN.T-1 uses=ADAE.AEDECOD,ADAE.TRTP,ADSL.SAFFL
source("setup.R")
"""
T1_HTML = ("<html><head><style>td{padding:2px}</style></head><body><table><thead><tr><th></th><th data-ard='0'>A (N=2)</th><th data-ard='1'>B (N=1)</th></tr></thead>"
           "<tbody><tr><td>HEADACHE</td><td data-ard='2,3'>1 (50.0%)</td><td data-ard='4'>0</td></tr></tbody></table></body></html>")
T1_ARD = [
    {"variable": "BIGN", "stat_name": "N", "stat": 2, "group1": "TRTP", "group1_level": "A"},
    {"variable": "BIGN", "stat_name": "N", "stat": 1, "group1": "TRTP", "group1_level": "B"},
    {"variable": "AEDECOD", "variable_level": "HEADACHE", "stat_name": "n", "stat": 1, "group1": "TRTP", "group1_level": "A"},
    {"variable": "AEDECOD", "variable_level": "HEADACHE", "stat_name": "p", "stat": 0.5, "group1": "TRTP", "group1_level": "A"},
    {"variable": "AEDECOD", "variable_level": "HEADACHE", "stat_name": "n", "stat": 0, "group1": "TRTP", "group1_level": "B"},
]
LINEAGE = {
    "variables": [
        {"dataset": "ADSL", "variable": "USUBJID", "origin": "Predecessor", "program": "adsl.R", "lines": [8, 8], "sources": ["DM.USUBJID"]},
        {"dataset": "ADSL", "variable": "TRTP", "origin": "Derived", "program": "adsl.R", "lines": [11, 11], "sources": ["DM.ARM"], "method": "Planned treatment"},
        {"dataset": "ADSL", "variable": "SAFFL", "origin": "Derived", "program": "adsl.R", "lines": [14, 14], "sources": ["EX.EXSTDTC"]},
        {"dataset": "ADAE", "variable": "USUBJID", "origin": "Predecessor", "program": "adae.R", "lines": [7, 7], "sources": ["AE.USUBJID"]},
        {"dataset": "ADAE", "variable": "AEDECOD", "origin": "Predecessor", "program": "adae.R", "lines": [7, 7], "sources": ["AE.AEDECOD"]},
        {"dataset": "ADAE", "variable": "TRTP", "origin": "Predecessor", "program": "adae.R", "lines": [7, 7], "sources": ["ADSL.TRTP"]},
        {"dataset": "ADAE", "variable": "TRTEMFL", "origin": "Derived", "program": "adae.R", "lines": [10, 10], "sources": ["ADSL.NOTAVAR"]},
    ],
    "consumers": {"ADAE.AEDECOD": ["T-1"], "ADAE.TRTP": ["T-1"], "ADSL.SAFFL": ["T-1"]},
}
SPEC = {"protocol": "STUDY01", "datasets": [
    {"name": "ADSL", "class": "ADSL", "sdtm_source": ["DM", "EX"], "variables": [{"name": "USUBJID", "role": "subject"}, {"name": "TRTP", "role": "planned treatment"},
                                                                                 {"name": "SAFFL", "role": "safety flag"}]},
    {"name": "ADAE", "class": "OCCDS", "sdtm_source": ["AE"], "variables": [{"name": "USUBJID", "role": "subject"}, {"name": "AEDECOD", "role": "term"},
                                                                           {"name": "TRTP", "role": "treatment"}, {"name": "TRTEMFL", "role": "TEAE flag"}]}]}
ARS = {"analysisSets": [{"id": "AS.SAF", "label": "Safety", "condition": {"dataset": "ADSL", "variable": "SAFFL", "comparator": "EQ", "value": ["Y"]}}],
       "dataSubsets": [{"id": "DS.T-1", "label": "TRTEMFL = 'Y'", "compoundExpression": {"logicalOperator": "AND", "whereClauses": [
           {"condition": {"dataset": "ADAE", "variable": "TRTEMFL", "comparator": "EQ", "value": ["Y"]}}]}}],
       "methods": [{"id": "MTH.FREQ", "label": "Frequency"}], "analysisGroupings": [{"id": "GRP.TRT", "groupingDataset": "ADSL", "groupingVariable": "TRTP"}],
       "analyses": [{"id": "AN.T-1", "name": "AEs", "methodId": "MTH.FREQ", "analysisSetId": "AS.SAF", "dataSubsetId": "DS.T-1", "dataset": "ADAE",
                     "orderedGroupings": [{"order": 1, "groupingId": "GRP.TRT"}]}]}
PLAN = [{"final_id": "T-1", "candidate_id": "safety-ae", "type": "Table", "title": "Adverse events", "status": "planned",
         "traces_to": {"objective_ids": ["Objective_1"], "endpoint_ids": ["Endpoint_1"]}},
        {"final_id": "T-2", "candidate_id": "safety-labs", "type": "Table", "title": "Labs", "status": "planned", "traces_to": {"objective_ids": ["Objective_1"]}}]
USDM = {"study": {"name": "STUDY01", "versions": [{"titles": [{"text": "A synthetic study", "type": {"decode": "Official Study Title"}}], "studyDesigns": [{"objectives": [
    {"id": "Objective_1", "text": "Assess safety", "level": {"decode": "Primary Objective"},
     "endpoints": [{"id": "Endpoint_1", "text": "Adverse events", "level": {"decode": "Primary Endpoint"}, "purpose": "Safety"}]},
    {"id": "Objective_2", "text": "An objective nobody planned for", "level": {"decode": "Secondary Objective"}, "endpoints": []}]}]}]}}
CITATIONS = {"Objective_1": {"page": 7, "quote": "Assess safety"}, "Endpoint_1": {"page": 30, "quote": "adverse events"}}
DEFINE = """<?xml version="1.0"?><ODM xmlns="http://www.cdisc.org/ns/odm/v1.2" xmlns:def="http://www.cdisc.org/ns/def/v1.0"><Study><MetaDataVersion>
<ItemGroupDef OID="DM" Name="DM" def:Label="Demographics"><ItemRef ItemOID="DM.USUBJID"/><ItemRef ItemOID="DM.ARM"/></ItemGroupDef>
<ItemGroupDef OID="EX" Name="EX" def:Label="Exposure"><ItemRef ItemOID="EX.USUBJID"/><ItemRef ItemOID="EX.EXSTDTC"/></ItemGroupDef>
<ItemGroupDef OID="AE" Name="AE" def:Label="Adverse Events"><ItemRef ItemOID="AE.USUBJID"/><ItemRef ItemOID="AE.AEDECOD"/></ItemGroupDef>
<ItemDef OID="DM.USUBJID" Name="USUBJID" def:Label="Subject"/><ItemDef OID="DM.ARM" Name="ARM" def:Label="Description of Planned Arm"/>
<ItemDef OID="EX.USUBJID" Name="USUBJID" def:Label="Subject"/><ItemDef OID="EX.EXSTDTC" Name="EXSTDTC" def:Label="Start Date"/>
<ItemDef OID="AE.USUBJID" Name="USUBJID" def:Label="Subject"/><ItemDef OID="AE.AEDECOD" Name="AEDECOD" def:Label="Dictionary-Derived Term"/>
</MetaDataVersion></Study></ODM>"""
CORE = {"Conformance_Details": {"Version": "V3.4", "CORE_Engine_Version": "1.0.0"}, "Rules_Report": [{"core_id": "CORE-1"}],
        "Issue_Summary": [{"core_id": "CORE-1", "dataset": "DM", "message": "ARM is odd", "issues": 1}],
        "Issue_Details": [{"core_id": "CORE-1", "dataset": "DM", "USUBJID": "S1", "row": 1, "variables": ["ARM"], "values": ["A"]}]}
DISPOSITIONS = {"dispositions": {"CORE-1|DM": {"disposition": "justified", "justification": "synthetic"}}}
ACCURACY = {"denominators": {"T-1": {"status": "pass"}}, "recompute": {"T-1": {"statistics": 3, "recomputed": 3, "mismatches": []}},
            "summary": {"denominatorsPassed": 1}, "coverage": {"statistics": 3, "recomputed": 3, "mismatches": 0}}

ADAM_R = """library(haven)
args <- commandArgs(TRUE)
adsl <- data.frame(USUBJID = c("S1", "S2", "S3"), TRTP = c("A", "A", "B"), SAFFL = c("Y", "Y", "Y"))
adae <- data.frame(USUBJID = c("S1"), AEDECOD = c("HEADACHE"), TRTP = c("A"), TRTEMFL = c("Y"))
write_xpt(adsl, file.path(args[1], "adsl.xpt")); write_xpt(adae, file.path(args[1], "adae.xpt"))
"""


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (bytes, bytearray)):
        path.write_bytes(content)
    else:
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


def make_package(root: Path, with_data: bool) -> None:
    files = {
        "adam-program/adsl.R": ADSL_R, "adam-program/adae.R": ADAE_R, "adam-spec/adam-spec.json": SPEC, "lineage/lineage.json": LINEAGE,
        "ars/reporting-event.json": ARS, "tlf-plan/tlf-plan.json": PLAN, "usdm/usdm.json": USDM, "usdm-citations/usdm-citations.json": CITATIONS,
        "ard/T-1.json": T1_ARD, "tfl/T-1.html": T1_HTML, "tfl-program/T-1.R": T1_R, "tfl/accuracy.json": ACCURACY,
        "tfl/reconciliation.json": {"T-1": {"checked": 4, "unmatched": []}}, "sdtm-define/define.xml": DEFINE,
        "core-report-sdtmig/core-report.json": CORE, "core-dispositions-sdtmig/core-dispositions-sdtmig.json": DISPOSITIONS,
        "analysis-spec/analysis-spec.json": [{"table_id": "T-1", "title": "Adverse events", "methods": [{"label": "Frequency"}]}],
    }
    for relative, content in files.items():
        write(root / relative, content)
    if with_data:
        (root / "adam").mkdir()
        subprocess.run(["Rscript", "--vanilla", "-e", ADAM_R, str(root / "adam")], check=True, capture_output=True)


def reaches_sdtm(model: dict, ref: str, seen: set[str] | None = None) -> bool:
    seen = seen or set()
    variable = model["vars"].get(ref)
    if variable is None:
        return ref in model["sdtm"]
    if ref in seen:
        return False
    seen.add(ref)
    return any(reaches_sdtm(model, source, seen) for source in variable["sources"])


def check_model(model: dict) -> None:
    output = model["outputs"]["T-1"]
    rows = output["ard"]["rows"]
    variable_index = output["ard"]["cols"].index("variable")
    cells = re.findall(r"data-ard='([\d,]+)'", output["html"])
    assert cells, "fixture display has data-ard cells"
    for cell in cells:
        for index in map(int, cell.split(",")):
            target = output["resolve"][rows[index][variable_index]]
            assert target is not None and reaches_sdtm(model, target), f"cell row {index} -> {target} does not reach SDTM"
    assert output["resolve"]["BIGN"] == "ADSL.SAFFL", output["resolve"]
    assert output["objectives"] == ["Objective_1"] and output["endpoints"] == ["Endpoint_1"]

    for entry in LINEAGE["variables"]:
        variable = model["vars"][f"{entry['dataset']}.{entry['variable']}"]
        assert variable["inLineage"] is True and variable["steps"], variable["id"]
    saffl = model["vars"]["ADSL.SAFFL"]
    assert [step.get("target") for step in saffl["steps"][1:3]] == ["exposed", "ex"], saffl["steps"]
    assert saffl["steps"][2]["note"] == "reads SDTM EX" and "EX.EXSTDTC" in saffl["found"], saffl
    assert saffl["hi"] == [14]
    assert "ADAE.TRTP" in model["vars"]["ADSL.TRTP"]["usedBy"]

    gaps = {(gap["kind"], gap["ref"]) for gap in model["gaps"]}
    assert ("lineage", "ADAE.TRTEMFL") in gaps, "seeded broken @derive src is a gap"
    assert ("plan", "T-2") in gaps, "planned output with no result is a gap"
    assert ("protocol", "Objective_2") in gaps, "objective with no output is a gap"

    finding = model["core"]["findings"][0]
    assert finding["disposition"] == "justified" and finding["impact"]["sdtm"] == ["DM.ARM"], finding
    assert "ADSL.TRTP" in finding["impact"]["adam"] and "ADAE.TRTP" in finding["impact"]["downstream"]
    assert finding["impact"]["outputs"] == ["T-1"] and output["core"] == [finding["key"]]


def check_html(html: str) -> None:
    data = re.search(r'<script id="DATA" type="application/json">(.*?)</script>', html, re.S)
    assert data is not None, "DATA script present"
    json.loads(data.group(1))
    assert re.search(r'(src|href)="https?:', html) is None, "no external requests"
    assert "/*__SCRIPT__*/" not in html and "/*__DATA__*/" not in html


def test_model_and_page(with_data: bool) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch) / "package"
        make_package(root, with_data)
        check_model(build_model(root, {}))
        model = build(root, Path(scratch) / "out")
        check_model(model)
        check_html((Path(scratch) / "out" / "traceability-explorer.html").read_text(encoding="utf-8"))
        if with_data:
            profile = model["vars"]["ADSL.TRTP"]["profile"]
            assert profile["n"] == 3 and profile["byArm"]["arms"] == ["A", "B"], profile
            assert not [gap for gap in model["gaps"] if gap["kind"] == "data"], model["gaps"]
        else:
            assert any(gap["kind"] == "data" for gap in model["gaps"]), "missing profiles are reported"


def test_odd_inputs_are_gaps() -> None:
    """A package that skipped the upstream gates (standalone run): malformed tags and lineage become gaps, not crashes."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch) / "package"
        make_package(root, with_data=False)
        odd = json.loads(json.dumps(LINEAGE))
        odd["variables"][1]["sources"] = ["DM"]
        odd["variables"][2]["lines"] = ["14", "x"]
        write(root / "lineage" / "lineage.json", odd)
        write(root / "tfl-program" / "T-1.R", T1_R.replace("uses=ADAE.AEDECOD,", "uses=AEDECOD,"))
        write(root / "tfl" / "L-1.html", "<html><body><table><tr><td>listing</td></tr></table></body></html>")
        write(root / "ard" / "T-1.json", T1_ARD + [{"variable": None, "stat_name": "n", "stat": 1}])
        for path in ("usdm", "core-report-sdtmig", "sdtm-define", "ars"):
            shutil.rmtree(root / path)
        model = build_model(root, {})
        gaps = {(gap["kind"], gap["ref"]) for gap in model["gaps"]}
        assert ("lineage", "ADSL.SAFFL") in gaps, gaps
        assert ("number", "T-1") in gaps and ("output", "L-1") in gaps, gaps
        assert model["vars"]["ADSL.TRTP"]["sources"] == ["DM"]


def run_script(script: str, work: Path, step_input: dict, name: str) -> tuple[int, dict, Path]:
    scripts = work / "scripts"
    if scripts.exists() is False:
        shutil.copytree(SCRIPTS, scripts, ignore=shutil.ignore_patterns("__pycache__"))
        for helper in SHARED.glob("*.py"):
            shutil.copyfile(helper, scripts / helper.name)
    output = work / name
    output.mkdir()
    (output / "input.json").write_text(json.dumps(step_input))
    completed = subprocess.run([sys.executable, str(scripts / script)], capture_output=True, text=True,
                               env={**os.environ, "MEDIFORCE_OUTPUT_DIR": str(output), "RUN_ID": "trace", "STEP_ID": name})
    assert (output / "result.json").is_file(), completed.stderr
    return completed.returncode, json.loads((output / "result.json").read_text()), output


def test_steps() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        root = work / "package"
        make_package(root, with_data=False)
        write(root / "sdtm" / "dm.xpt", b"not read")
        write(root / "tfl" / "tlf-viewer.html", "<html></html>")
        entries = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                kind = path.parent.name
                entries.append({"name": path.name, "kind": kind, "downloadUrl": f"/api/runs/r/files/{kind}/{path.name}",
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "_local": str(path)})
        package = {"files": [{key: value for key, value in entry.items() if key != "_local"} for entry in entries], "history": []}

        code, result, _ = run_script("resolve_inputs.py", work, {"package": {}}, "empty")
        assert code == 1 and "No study package" in result["error"], result
        code, result, _ = run_script("resolve_inputs.py", work, {"package": package}, "resolve-inputs")
        assert code == 0, result
        names = {(entry["kind"], entry["name"]) for entry in result["files"]}
        assert ("sdtm", "dm.xpt") not in names and ("tfl", "tlf-viewer.html") not in names and ("lineage", "lineage.json") in names, names

        local = {(entry["kind"], entry["name"]): entry["_local"] for entry in entries}
        downloaded = [{**entry, "localPath": local[(entry["kind"], entry["name"])]} for entry in result["files"]]
        code, built, output = run_script("build_step.py", work, {"files": downloaded, "package": package}, "build-explorer")
        assert code == 0, built
        assert built["outcome"] == "traced" and built["gaps"] >= 3, built
        assert (output / "traceability-explorer.html").is_file() and (output / "traceability.json").is_file()
        traced = [entry for entry in built["package"]["files"] if entry["kind"] == "traceability"]
        assert sorted(entry["name"] for entry in traced) == ["traceability-explorer.html", "traceability.json"], traced
        assert traced[0]["downloadUrl"].startswith("/api/runs/trace/files/.mediforce/output/build-explorer/"), traced[0]
        assert built["package"]["history"][-1]["workflow"] == "trace-deliverables"

        tampered = [dict(entry, sha256="0" * 64) if entry["kind"] == "lineage" else entry for entry in downloaded]
        code, failed, _ = run_script("build_step.py", work, {"files": tampered, "package": package}, "tampered")
        assert code == 1 and "sha256 mismatch" in failed["error"], failed


def main() -> None:
    test_model_and_page(with_data=False)
    if shutil.which("Rscript") is not None:
        test_model_and_page(with_data=True)
    else:
        print("SKIP data profiles: Rscript not found")
    test_odd_inputs_are_gaps()
    test_steps()
    print("PASS trace-deliverables")


if __name__ == "__main__":
    main()
