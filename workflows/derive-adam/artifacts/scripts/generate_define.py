"""Generate the ADaM Define-XML 2.1 from what was actually derived.

Metadata comes from the executed datasets and the checked lineage, not from the
spec's intentions: names, types, lengths and labels from manifest.json; origin,
predecessor and method from lineage.json. So the define describes the delivered
data and points each derived variable at the program lines that make it.

Writes /output/define.xml.
Result: { datasets, variables, methods, summary }
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adamlib import INPUTS_DIR  # noqa: E402
from mfpkg import OUTPUT_DIR, STEP_OUTPUTS_DIR, StepFailure, now_iso, read_input, run_main, step_output, write_result  # noqa: E402

ODM = "http://www.cdisc.org/ns/odm/v1.3"
DEF = "http://www.cdisc.org/ns/def/v2.1"
XLINK = "http://www.w3.org/1999/xlink"
ElementTree.register_namespace("", ODM)
ElementTree.register_namespace("def", DEF)
ElementTree.register_namespace("xlink", XLINK)

CLASSES = {
    "ADSL": ("SUBJECT LEVEL ANALYSIS DATASET", "One record per subject"),
    "BDS": ("BASIC DATA STRUCTURE", "One record per subject per parameter per analysis timepoint"),
    "TTE": ("BASIC DATA STRUCTURE", "One record per subject per parameter"),
    "OCCDS": ("OCCURRENCE DATA STRUCTURE", "One record per subject per occurrence"),
}
DATA_TYPES = {"text": "text", "integer": "integer", "float": "float", "date": "integer", "datetime": "integer"}


def odm(tag: str) -> str:
    return f"{{{ODM}}}{tag}"


def define(tag: str) -> str:
    return f"{{{DEF}}}{tag}"


def text_child(parent: ElementTree.Element, tag: str, text: str) -> None:
    holder = ElementTree.SubElement(parent, tag)
    translated = ElementTree.SubElement(holder, odm("TranslatedText"), {"{http://www.w3.org/XML/1998/namespace}lang": "en"})
    translated.text = text


def load(step: str, name: str) -> dict:
    path = STEP_OUTPUTS_DIR / step / name
    if path.is_file() is False:
        raise StepFailure(f"{step} left no {name} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build(manifests: list[dict], lineage: dict, spec: dict, profile: dict, study_id: str) -> tuple[ElementTree.Element, int]:
    version = str(profile.get("adamig") or "1-3").replace("-", ".")
    root = ElementTree.Element(odm("ODM"), {
        "FileType": "Snapshot", "FileOID": f"DEF.{study_id}.ADAM", "ODMVersion": "1.3.2",
        "CreationDateTime": now_iso(), "Originator": "Mediforce derive-adam", define("Context"): "Submission",
    })
    study = ElementTree.SubElement(root, odm("Study"), {"OID": f"ST.{study_id}"})
    global_variables = ElementTree.SubElement(study, odm("GlobalVariables"))
    for tag, value in (("StudyName", study_id), ("StudyDescription", f"{study_id} ADaM"), ("ProtocolName", study_id)):
        ElementTree.SubElement(global_variables, odm(tag)).text = value
    metadata = ElementTree.SubElement(study, odm("MetaDataVersion"), {
        "OID": f"MDV.{study_id}.ADaMIG.{version}", "Name": f"{study_id} ADaM", define("DefineVersion"): "2.1.0",
    })
    standards = ElementTree.SubElement(metadata, define("Standards"))
    ElementTree.SubElement(standards, define("Standard"), {
        "OID": "STD.ADaMIG", "Name": "ADaMIG", "Type": "IG", "Version": version, "Status": "Final",
    })

    by_variable = {f"{entry['dataset']}.{entry['variable']}": entry for entry in lineage.get("variables") or []}
    item_defs, method_defs = [], []
    for manifest in manifests:
        dataset = manifest["dataset"]
        demand = spec.get(dataset) or {}
        dataset_class = str(demand.get("class") or ("ADSL" if dataset == "ADSL" else "BDS")).upper()
        class_name, structure = CLASSES.get(dataset_class, CLASSES["BDS"])
        group = ElementTree.SubElement(metadata, odm("ItemGroupDef"), {
            "OID": f"IG.{dataset}", "Name": dataset, "SASDatasetName": dataset, "Repeating": "No" if dataset == "ADSL" else "Yes",
            "IsReferenceData": "No", "Purpose": "Analysis", define("Structure"): structure, define("StandardOID"): "STD.ADaMIG",
            define("ArchiveLocationID"): f"LF.{dataset}",
        })
        text_child(group, odm("Description"), str(demand.get("label") or f"{dataset} ({class_name.title()})"))
        for order, column in enumerate(manifest["columns"], start=1):
            key = f"{dataset}.{column['name']}"
            entry = by_variable.get(key, {})
            attributes = {"ItemOID": f"IT.{key}", "Mandatory": "Yes" if column["name"] in ("STUDYID", "USUBJID") else "No", "OrderNumber": str(order)}
            if entry.get("origin") == "Derived":
                attributes["MethodOID"] = f"MT.{key}"
                method_defs.append((key, entry))
            ElementTree.SubElement(group, odm("ItemRef"), attributes)
            item_defs.append((key, column, entry))
        class_element = ElementTree.SubElement(group, define("Class"), {"Name": class_name})
        if dataset_class == "TTE":
            ElementTree.SubElement(class_element, define("SubClass"), {"Name": "TIME-TO-EVENT"})
        leaf = ElementTree.SubElement(group, define("leaf"), {"ID": f"LF.{dataset}", f"{{{XLINK}}}href": f"{dataset.lower()}.xpt"})
        ElementTree.SubElement(leaf, define("title")).text = f"{dataset.lower()}.xpt"

    for key, column, entry in item_defs:
        attributes = {"OID": f"IT.{key}", "Name": column["name"], "SASFieldName": column["name"], "DataType": DATA_TYPES[column["type"]]}
        attributes["Length"] = str(column["length"])
        if column["type"] == "float":
            attributes[define("SignificantDigits")] = str(column.get("digits", 0))
        if column.get("format"):
            attributes[define("DisplayFormat")] = column["format"]
        item = ElementTree.SubElement(metadata, odm("ItemDef"), attributes)
        text_child(item, odm("Description"), column["label"])
        origin = ElementTree.SubElement(item, define("Origin"), {"Type": entry.get("origin") or "Derived"})
        if entry.get("origin") == "Predecessor" and entry.get("sources"):
            text_child(origin, odm("Description"), ", ".join(entry["sources"]))

    programs = sorted({entry.get("program") for _, entry in method_defs if entry.get("program")})
    for key, entry in method_defs:
        method = ElementTree.SubElement(metadata, odm("MethodDef"), {"OID": f"MT.{key}", "Name": f"Algorithm for {key}", "Type": "Computation"})
        lines = entry.get("lines") or []
        sources = ", ".join(entry.get("sources") or [])
        parts = [entry.get("method") or f"Derived in {entry.get('program')}",
                 f"Sources: {sources}." if sources else "",
                 f"Program {entry.get('program')} lines {lines[0]}-{lines[1]}." if len(lines) == 2 else ""]
        text_child(method, odm("Description"), " ".join(part for part in parts if part))
        if entry.get("program"):
            ElementTree.SubElement(method, define("DocumentRef"), {"leafID": f"LF.PRG.{entry['program']}"})
    for program in programs:
        leaf = ElementTree.SubElement(metadata, define("leaf"), {"ID": f"LF.PRG.{program}", f"{{{XLINK}}}href": program})
        ElementTree.SubElement(leaf, define("title")).text = program
    return root, len(method_defs)


def main() -> None:
    step_input = read_input()
    manifests = load("execute-programs", "manifest.json").get("datasets") or []
    if not manifests:
        raise StepFailure("No derived datasets to describe.")
    lineage = load("check-lineage", "lineage.json")
    spec_document = json.loads((INPUTS_DIR / "adam-spec.json").read_text(encoding="utf-8"))
    spec = {str(dataset.get("name", "")).upper(): dataset for dataset in spec_document.get("datasets") or []}
    package = step_output(step_input, "resolve-inputs").get("package") or {}
    study_id = str((package.get("study") or {}).get("id") or spec_document.get("protocol") or os.environ.get("STUDY_ID", "STUDY"))

    root, methods = build(manifests, lineage, spec, package.get("profile") or {}, study_id)
    ElementTree.indent(root)
    target = OUTPUT_DIR / "define.xml"
    ElementTree.ElementTree(root).write(target, encoding="UTF-8", xml_declaration=True)
    variables = sum(len(manifest["columns"]) for manifest in manifests)
    write_result({
        "datasets": len(manifests),
        "variables": variables,
        "methods": methods,
        "summary": f"define.xml (Define-XML 2.1, ADaMIG): {len(manifests)} dataset(s), {variables} variable(s), {methods} derivation method(s) linked to program lines.",
    })


if __name__ == "__main__":
    run_main(main)
