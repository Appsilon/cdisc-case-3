"""Build the traceability model (traceability.json) of one study package.

The package folder holds the run's files as <kind>/<name> (the layout
tools/fetch_package.py writes and build_step.py stages). Every link comes from
data the earlier workflows already wrote; nothing is inferred by an AI:

  TLF cell  --data-ard-->  ARD rows  --@tlf analysis=/uses=-->  ARS analysis + ADaM variables
  ADaM var  --lineage.json (@derive)-->  program lines + declared SDTM / ADaM sources
            --rcode.trace-->  the earlier statements those lines read, down to read_sdtm()
  output    --tlf-plan traces_to-->  USDM endpoint / objective  --usdm-citations-->  protocol page + quote
  CORE finding (dataset, variables)  --sources-->  ADaM variables  --consumers-->  outputs
  checks    reconciliation.json, accuracy.json, population-counts.json per output

A link that should exist and does not becomes an entry in `gaps`, never a crash.

    build_model(Path("handover/e2e-a48c3201"), profiles) -> dict
"""

from __future__ import annotations

import base64
import json
import re
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from pathlib import Path

from rcode import RProgram

STANDARDS = ("usdm", "sdtmig", "adamig")
TLF_TAG = re.compile(r"#\s*@tlf\s+(\S+)(.*)")
KEY_COLUMNS = {"STUDYID", "USUBJID", "DOMAIN", "SUBJID"}
EXAMPLES_PER_FINDING = 5


def read_json(path: Path, default=None):
    if path.is_file() is False:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return default


def kind_files(root: Path, kind: str, pattern: str = "*") -> list[Path]:
    folder = root / kind
    return sorted(path for path in folder.glob(pattern) if path.is_file()) if folder.is_dir() else []


class Model:
    def __init__(self, root: Path, profiles: dict):
        self.root = root
        self.profiles = profiles or {}
        self.gaps: list[dict] = []
        self.vars: dict[str, dict] = {}
        self.sdtm: dict[str, dict] = {}
        self.programs: dict[str, str] = {}
        self.outputs: dict[str, dict] = {}
        self.analyses: dict[str, dict] = {}
        self.findings: list[dict] = []

    def gap(self, kind: str, ref: str, message: str) -> None:
        self.gaps.append({"kind": kind, "ref": ref, "message": message})

    # ---------------------------------------------------------------- SDTM

    def load_sdtm_define(self) -> dict[str, dict]:
        """domain -> {label, columns: {name: label}} from the SDTM define.xml, when supplied."""
        domains: dict[str, dict] = {}
        defines = kind_files(self.root, "sdtm-define", "*.xml")
        if len(defines) == 0:
            return domains
        try:
            tree = ElementTree.parse(defines[0])
        except ElementTree.ParseError:
            self.gap("input", defines[0].name, "The SDTM define.xml does not parse; SDTM column labels are missing.")
            return domains
        items, groups = {}, []
        for element in tree.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            label = next((value for key, value in element.attrib.items() if key.rsplit("}", 1)[-1] == "Label"), "")
            if tag == "ItemDef":
                items[element.get("OID")] = (element.get("Name"), label)
            elif tag == "ItemGroupDef":
                refs = [child.get("ItemOID") for child in element if child.tag.rsplit("}", 1)[-1] == "ItemRef"]
                groups.append((element.get("Name") or element.get("OID"), label, refs))
        for name, label, refs in groups:
            columns = {}
            for ref in refs:
                if ref in items and items[ref][0]:
                    columns[items[ref][0]] = items[ref][1]
            domains[str(name).upper()] = {"label": label, "columns": columns}
        return domains

    def sdtm_column(self, ref: str) -> dict:
        if ref not in self.sdtm:
            domain, _, column = ref.partition(".")
            label = ((self.domains.get(domain) or {}).get("columns") or {}).get(column, "")
            self.sdtm[ref] = {"label": label, "usedBy": [], "readBy": [], "core": []}
        return self.sdtm[ref]

    # ---------------------------------------------------------------- ADaM lineage

    def load_lineage(self) -> None:
        lineage = read_json(self.root / "lineage" / "lineage.json", {}) or {}
        spec = read_json(self.root / "adam-spec" / "adam-spec.json", {}) or {}
        self.spec_datasets = {str(dataset.get("name", "")).upper(): dataset for dataset in spec.get("datasets") or []}
        self.spec_protocol = spec.get("protocol")
        self.domains = self.load_sdtm_define()
        for path in kind_files(self.root, "adam-program", "*.R"):
            self.programs[f"adam/{path.name}"] = path.read_text(encoding="utf-8", errors="replace")
        parsed = {name: RProgram(text) for name, text in self.programs.items()}
        consumers = lineage.get("consumers") or {}

        for entry in lineage.get("variables") or []:
            var_id = f"{entry.get('dataset')}.{entry.get('variable')}"
            sources = [str(source) for source in entry.get("sources") or []]
            self.vars[var_id] = {
                "id": var_id, "ds": entry.get("dataset"), "name": entry.get("variable"), "origin": entry.get("origin"),
                "method": entry.get("method"), "spec": entry.get("spec"), "program": entry.get("program"),
                "lines": entry.get("lines"), "sources": sources, "outputs": sorted(consumers.get(var_id) or []),
                "steps": [], "found": [], "deps": [], "usedBy": [], "analyses": [], "endpoints": [], "objectives": [],
                "core": [], "flags": [], "inLineage": True,
            }
        for dataset_name, dataset in self.spec_datasets.items():
            for variable in dataset.get("variables") or []:
                var_id = f"{dataset_name}.{variable.get('name')}"
                if var_id not in self.vars:
                    self.vars[var_id] = {"id": var_id, "ds": dataset_name, "name": variable.get("name"), "sources": [], "outputs": [],
                                         "steps": [], "found": [], "deps": [], "usedBy": [], "analyses": [], "endpoints": [],
                                         "objectives": [], "core": [], "flags": [], "inLineage": False}
                    self.gap("lineage", var_id, "In the ADaM spec but has no @derive entry in lineage.json.")
                self.vars[var_id]["role"] = variable.get("role")
                self.vars[var_id]["inSpec"] = True
        for dataset_name, profile in self.profiles.items():
            for column, column_profile in (profile.get("columns") or {}).items():
                var_id = f"{dataset_name}.{column}"
                if var_id not in self.vars:
                    self.vars[var_id] = {"id": var_id, "ds": dataset_name, "name": column, "sources": [], "outputs": [], "steps": [],
                                         "found": [], "deps": [], "usedBy": [], "analyses": [], "endpoints": [], "objectives": [],
                                         "core": [], "flags": [], "inLineage": False}
                    self.gap("lineage", var_id, "In the ADaM data but has no @derive entry in lineage.json.")
                self.vars[var_id]["profile"] = column_profile
                self.vars[var_id]["label"] = column_profile.get("label")
                self.vars[var_id]["inData"] = True

        for var in self.vars.values():
            var.setdefault("inSpec", False)
            var.setdefault("inData", False)
            if var["inSpec"] is False and var["inLineage"] is True:
                var["flags"].append("not in the ADaM spec")
            if var["inData"] is False and len(self.profiles) > 0:
                var["flags"].append("not in the delivered ADaM data")
                self.gap("data", var["id"], "Has a lineage entry but is not a column of the delivered ADaM dataset.")
            self.trace_code(var, parsed)
            for source in var["sources"]:
                domain, _, column_name = source.partition(".")
                if source in self.vars:
                    self.vars[source]["usedBy"].append(var["id"])
                elif domain in self.spec_datasets:
                    var["flags"].append(f"declared source {source} is not an ADaM variable")
                    self.gap("lineage", var["id"], f"Declared source {source} is not an ADaM variable of this run.")
                else:
                    self.sdtm_column(source)["usedBy"].append(var["id"])
                    if domain in self.domains and column_name not in self.domains[domain]["columns"]:
                        var["flags"].append(f"declared source {source} is not in the SDTM define.xml")
        for var in self.vars.values():
            var["usedBy"] = sorted(set(var["usedBy"]))
            for dependency in var["deps"]:
                if dependency in self.vars and var["id"] not in self.vars[dependency]["usedBy"]:
                    self.vars[dependency]["usedBy"].append(var["id"])

    def trace_code(self, var: dict, parsed: dict[str, RProgram]) -> None:
        program = parsed.get(f"adam/{var.get('program')}")
        lines = var.get("lines") or []
        if program is None or len(lines) != 2 or all(isinstance(line, int) for line in lines) is False:
            if var["inLineage"] is True:
                var["flags"].append("no program lines")
                self.gap("lineage", var["id"], f"No usable program lines in lineage.json (program {var.get('program')}, lines {lines}).")
            return
        start, end = lines
        own_frame = str(var["ds"]).lower()
        block = program.covering(start, end)
        traced = program.trace(start, end, own_frame)
        var["steps"] = [{"file": f"adam/{var['program']}", "s": start, "e": end, "kind": "primary"}]
        for statement in traced:
            note = ""
            if len(statement.loads) > 0:
                note = "reads " + ", ".join(f"{kind.upper()} {name}" for kind, name in statement.loads)
            elif statement.defines_function:
                note = f"defines the helper {statement.target}()"
            var["steps"].append({"file": f"adam/{var['program']}", "s": statement.start, "e": statement.end, "kind": "upstream",
                                 "target": statement.target, "note": note})
        # SDTM / ADaM columns named in the code that runs, per dataset read along the trace
        loads = [load for statement in traced + block for load in statement.loads]
        assigning = program.assigning_lines(start, end, var["name"])
        var["hi"] = assigning or program.lines_naming(start, end, var["name"])
        block_tokens = program.tokens_in(start, end)
        own_tokens = {token for line in assigning for token in program.tokens_in(line, line)}
        tokens = block_tokens | {token for statement in traced for token in statement.tokens}
        found = set()
        for kind, name in loads:
            if kind == "sdtm":
                for column in (self.domains.get(name) or {}).get("columns") or {}:
                    if column in tokens and column not in KEY_COLUMNS:
                        found.add(f"{name}.{column}")
                        self.sdtm_column(f"{name}.{column}")["readBy"].append(var["id"])
        var["found"] = sorted(found)
        deps = set()
        for token in own_tokens:
            if token == var["name"] or token in KEY_COLUMNS:
                continue
            for dataset in {var["ds"]} | {name for kind, name in loads if kind == "adam"}:
                if f"{dataset}.{token}" in self.vars:
                    deps.add(f"{dataset}.{token}")
        var["deps"] = sorted(deps)
        read_domains = {name for kind, name in loads if kind == "sdtm"}
        if len(self.domains) > 0 and len(read_domains) > 0:
            unread = [source for source in var["sources"] if source not in found and source.partition(".")[0] in read_domains
                      and source.partition(".")[2] not in KEY_COLUMNS]
            if len(unread) > 0:
                var["flags"].append("declared but not named in the traced code: " + ", ".join(unread))

    # ---------------------------------------------------------------- outputs

    def load_outputs(self) -> None:
        ars = read_json(self.root / "ars" / "reporting-event.json", {}) or {}
        sets = {entry.get("id"): entry for entry in ars.get("analysisSets") or []}
        subsets = {entry.get("id"): entry for entry in ars.get("dataSubsets") or []}
        methods = {entry.get("id"): entry for entry in ars.get("methods") or []}
        groupings = {entry.get("id"): entry for entry in ars.get("analysisGroupings") or []}
        for analysis in ars.get("analyses") or []:
            analysis_set = sets.get(analysis.get("analysisSetId")) or {}
            subset = subsets.get(analysis.get("dataSubsetId")) or {}
            condition = analysis_set.get("condition") or {}
            subset_vars = sorted({f"{clause['condition'].get('dataset')}.{clause['condition'].get('variable')}"
                                  for clause in self.where_clauses(subset) if clause.get("condition")})
            self.analyses[analysis.get("id")] = {
                "id": analysis.get("id"), "name": analysis.get("name"), "dataset": analysis.get("dataset"),
                "method": (methods.get(analysis.get("methodId")) or {}).get("label") or (methods.get(analysis.get("methodId")) or {}).get("name"),
                "analysisSet": {"id": analysis_set.get("id"), "label": analysis_set.get("label") or analysis_set.get("name"),
                                "var": f"{condition.get('dataset')}.{condition.get('variable')}" if condition.get("variable") else None,
                                "condition": " ".join(str(part) for part in (condition.get("variable"), condition.get("comparator"),
                                                                              ",".join(map(str, condition.get("value") or [])))) if condition else ""},
                "dataSubset": {"label": subset.get("label"), "vars": subset_vars},
                "groupings": [{"id": grouping.get("groupingId"),
                               "var": f"{(groupings.get(grouping.get('groupingId')) or {}).get('groupingDataset')}."
                                      f"{(groupings.get(grouping.get('groupingId')) or {}).get('groupingVariable')}"}
                              for grouping in analysis.get("orderedGroupings") or []],
            }
        specs = {entry.get("table_id"): entry for entry in read_json(self.root / "analysis-spec" / "analysis-spec.json", []) or []}
        plan = read_json(self.root / "tlf-plan" / "tlf-plan.json", []) or []
        planned = {entry.get("final_id"): entry for entry in plan if entry.get("final_id")}
        accuracy = read_json(self.root / "tfl" / "accuracy.json", {}) or {}
        reconciliation = read_json(self.root / "tfl" / "reconciliation.json", {}) or {}
        for path in kind_files(self.root, "tfl-program", "*.R"):
            self.programs[f"tlf/{path.name}"] = path.read_text(encoding="utf-8", errors="replace")

        displays = {path.stem for path in kind_files(self.root, "tfl", "*.html") if path.name != "tlf-viewer.html"}
        ards = {path.stem for path in kind_files(self.root, "ard", "*.json")}
        for output_id in sorted(displays | ards):
            program_name = f"tlf/{output_id}.R"
            tag = TLF_TAG.search(self.programs.get(program_name, ""))
            fields = dict(re.findall(r"(\w+)=(\S+)", tag.group(2))) if tag else {}
            uses = [use for use in fields.get("uses", "").split(",") if use]
            analysis_id = fields.get("analysis")
            if tag is None:
                self.gap("output", output_id, "The program has no @tlf tag (or there is no program): no ADaM trace.")
            if analysis_id is not None and analysis_id not in self.analyses:
                self.gap("output", output_id, f"Analysis {analysis_id} is not in the ARS ReportingEvent.")
            html_path = self.root / "tfl" / f"{output_id}.html"
            png_path = self.root / "tfl" / f"{output_id}.png"
            plan_entry = planned.get(output_id) or {}
            spec = specs.get(output_id) or {}
            output = {
                "id": output_id, "title": plan_entry.get("title") or spec.get("title") or output_id,
                "type": plan_entry.get("type") or ("Figure" if output_id.startswith("F") else "Listing" if output_id.startswith("L") else "Table"),
                "html": html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else None,
                "png": "data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode() if png_path.is_file() else None,
                "program": program_name if program_name in self.programs else None, "analysis": analysis_id, "uses": uses,
                "ard": self.compact_ard(read_json(self.root / "ard" / f"{output_id}.json", None)),
                "plan": {key: plan_entry.get(key) for key in ("candidate_id", "category", "priority", "status", "traces_to", "notes", "analysis")}
                        if plan_entry else None,
                "spec": {"purpose": spec.get("purpose"), "analysisSet": (spec.get("analysisSet") or {}).get("label"),
                         "subset": (spec.get("dataSubset") or {}).get("condition"),
                         "methods": [method.get("label") for method in spec.get("methods") or []]} if spec else None,
                "checks": {"reconciliation": reconciliation.get(output_id), "denominators": (accuracy.get("denominators") or {}).get(output_id),
                           "recompute": (accuracy.get("recompute") or {}).get(output_id)},
                "objectives": [], "endpoints": [], "core": [],
            }
            if output["html"] is None:
                self.gap("output", output_id, "There is an ARD but no rendered display.")
            if output["ard"] is None:
                self.gap("output", output_id, "There is a display but no ARD.")
            if len(plan_entry) == 0:
                self.gap("plan", output_id, "Not in the TLF plan.")
            for use in uses:
                if use not in self.vars:
                    self.gap("output", output_id, f"Uses {use}, which has no lineage entry.")
                elif output_id not in self.vars[use]["outputs"]:
                    self.vars[use]["outputs"].append(output_id)
            output["resolve"] = self.resolve_ard_names(output)
            self.outputs[output_id] = output
        for entry in plan:
            if entry.get("final_id") and entry.get("status") == "planned" and entry["final_id"] not in self.outputs:
                self.gap("plan", entry["final_id"], "Planned, but the run produced no output for it.")
        self.plan = [{"id": entry.get("final_id") or entry.get("candidate_id"), "title": entry.get("title"), "type": entry.get("type"),
                      "status": entry.get("status"), "reason": entry.get("status_reason"), "priority": entry.get("priority"),
                      "traces": entry.get("traces_to") or {}, "produced": bool(entry.get("final_id") in self.outputs)} for entry in plan]

    @staticmethod
    def where_clauses(subset: dict) -> list[dict]:
        found, pending = [], [subset]
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                if "condition" in node and isinstance(node["condition"], dict):
                    found.append(node)
                pending.extend(value for key, value in node.items() if key != "condition")
            elif isinstance(node, list):
                pending.extend(node)
        return found

    @staticmethod
    def compact_ard(rows) -> dict | None:
        if isinstance(rows, list) is False:
            return None
        columns: list[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        return {"cols": columns, "rows": [[row.get(column) for column in columns] for row in rows]}

    def resolve_ard_names(self, output: dict) -> dict:
        """Each ARD variable / group variable name -> the ADaM variable it denotes, for this output."""
        analysis = self.analyses.get(output.get("analysis")) or {}
        dataset = analysis.get("dataset")
        names: set[str] = set()
        ard = output.get("ard") or {"cols": [], "rows": []}
        name_columns = [index for index, column in enumerate(ard["cols"]) if column == "variable" or re.fullmatch(r"group\d+", column)]
        for row in ard["rows"]:
            for index in name_columns:
                if isinstance(row[index], str) and row[index]:
                    names.add(row[index])
        resolved = {}
        for name in sorted(names):
            if name == "BIGN":
                resolved[name] = (analysis.get("analysisSet") or {}).get("var")
                continue
            candidates = [use for use in output["uses"] if use.partition(".")[2] == name]
            preferred = [use for use in candidates if use.partition(".")[0] == dataset]
            target = (preferred or candidates or [None])[0]
            if target is None:
                for fallback in (f"{dataset}.{name}", f"ADSL.{name}"):
                    if fallback in self.vars:
                        target = fallback
                        break
            resolved[name] = target
            if target is None:
                self.gap("number", output["id"], f"ARD variable {name} does not resolve to an ADaM variable (not in the @tlf uses).")
        return resolved

    # ---------------------------------------------------------------- protocol

    def load_protocol(self) -> dict:
        usdm = read_json(self.root / "usdm" / "usdm.json", {}) or {}
        citations = read_json(self.root / "usdm-citations" / "usdm-citations.json", {}) or {}
        version = ((usdm.get("study") or {}).get("versions") or [{}])[0]
        design = (version.get("studyDesigns") or [{}])[0]
        titles = version.get("titles") or []
        title = next((entry.get("text") for entry in titles if "official" in json.dumps(entry.get("type") or {}).lower()), None)
        objectives, endpoints = [], {}
        for objective in design.get("objectives") or []:
            endpoint_ids = []
            for endpoint in objective.get("endpoints") or []:
                endpoints[endpoint.get("id")] = {"id": endpoint.get("id"), "text": endpoint.get("text"),
                                                 "level": (endpoint.get("level") or {}).get("decode"), "purpose": endpoint.get("purpose"),
                                                 "objective": objective.get("id"), "cite": citations.get(endpoint.get("id")), "outputs": []}
                endpoint_ids.append(endpoint.get("id"))
            objectives.append({"id": objective.get("id"), "text": objective.get("text"), "level": (objective.get("level") or {}).get("decode"),
                               "cite": citations.get(objective.get("id")), "endpoints": endpoint_ids, "outputs": []})
        by_objective = {objective["id"]: objective for objective in objectives}
        for entry in self.plan:
            traces = entry.get("traces") or {}
            for objective_id in traces.get("objective_ids") or []:
                if objective_id in by_objective and entry["id"] not in by_objective[objective_id]["outputs"]:
                    by_objective[objective_id]["outputs"].append(entry["id"])
            for endpoint_id in traces.get("endpoint_ids") or []:
                if endpoint_id in endpoints and entry["id"] not in endpoints[endpoint_id]["outputs"]:
                    endpoints[endpoint_id]["outputs"].append(entry["id"])
            if entry["id"] in self.outputs:
                self.outputs[entry["id"]]["objectives"] = list(traces.get("objective_ids") or [])
                self.outputs[entry["id"]]["endpoints"] = list(traces.get("endpoint_ids") or [])
                self.outputs[entry["id"]]["rule"] = traces.get("regulatory_rule")
        for objective in objectives:
            if len(objective["outputs"]) == 0 and any(endpoints[endpoint_id]["outputs"] for endpoint_id in objective["endpoints"]) is False:
                self.gap("protocol", objective["id"], f"{objective.get('level') or 'Objective'} has no planned output.")
        for output_id, output in self.outputs.items():
            for var_id in output["uses"]:
                if var_id in self.vars:
                    var = self.vars[var_id]
                    for key, values in (("analyses", [output.get("analysis")]), ("endpoints", output["endpoints"]), ("objectives", output["objectives"])):
                        for value in values:
                            if value is not None and value not in var[key]:
                                var[key].append(value)
        identifiers = [entry.get("text") for entry in version.get("studyIdentifiers") or [] if entry.get("text")]
        study_id = self.spec_protocol or (identifiers[0] if identifiers else (usdm.get("study") or {}).get("name"))
        return {"study": {"id": study_id, "title": title, "identifiers": identifiers},
                "objectives": objectives, "endpoints": endpoints}

    # ---------------------------------------------------------------- CORE

    def load_core(self) -> dict:
        standards = {}
        for standard in STANDARDS:
            report = read_json(self.root / f"core-report-{standard}" / "core-report.json", None)
            dispositions = (read_json(self.root / f"core-dispositions-{standard}" / f"core-dispositions-{standard}.json", {}) or {}).get("dispositions") or {}
            if report is None:
                continue
            details = defaultdict(list)
            for issue in report.get("Issue_Details") or []:
                details[(issue.get("core_id"), issue.get("dataset") or "")].append(issue)
            conformance = report.get("Conformance_Details") or {}
            summary = report.get("Issue_Summary") or []
            standards[standard] = {"version": conformance.get("Version"), "engine": conformance.get("CORE_Engine_Version"),
                                   "runtime": conformance.get("Total_Runtime"), "generated": conformance.get("Report_Generation"),
                                   "rules": len(report.get("Rules_Report") or []), "findings": 0, "issues": 0}
            for item in summary:
                rule, dataset = item.get("core_id"), item.get("dataset") or ""
                issues = details.get((rule, dataset), [])
                variables = sorted({variable for issue in issues for variable in issue.get("variables") or []})
                subjects = sorted({issue.get("USUBJID") for issue in issues if issue.get("USUBJID")})
                disposition = dispositions.get(f"{rule}|{dataset}") or {}
                finding = {"key": f"{standard}|{rule}|{dataset}", "std": standard, "rule": rule, "dataset": dataset,
                           "message": item.get("message"), "issues": item.get("issues"), "variables": variables, "subjects": len(subjects),
                           "examples": [{"subject": issue.get("USUBJID"), "seq": issue.get("SEQ"), "row": issue.get("row"),
                                         "values": dict(zip(issue.get("variables") or [], issue.get("values") or []))}
                                        for issue in issues[:EXAMPLES_PER_FINDING]],
                           "disposition": disposition.get("disposition"), "justification": disposition.get("justification"),
                           "evaluationError": "rule evaluation error" in str(item.get("message") or "").lower()}
                finding["impact"] = self.core_impact(finding)
                self.findings.append(finding)
                standards[standard]["findings"] += 1
                standards[standard]["issues"] += int(item.get("issues") or 0)
        return standards

    def core_impact(self, finding: dict) -> dict:
        dataset = finding["dataset"].upper()
        direct: set[str] = set()
        touched: list[str] = []
        if finding["std"] == "adamig":
            for variable in finding["variables"]:
                if f"{dataset}.{variable}" in self.vars:
                    direct.add(f"{dataset}.{variable}")
        elif finding["std"] == "sdtmig":
            for variable in finding["variables"]:
                ref = f"{dataset}.{variable}"
                column = self.sdtm.get(ref)
                if column is not None:
                    touched.append(ref)
                    column["core"].append(finding["key"])
                    direct.update(column["usedBy"])
                    direct.update(column["readBy"])
        downstream, pending = set(), list(direct)
        while pending:
            var_id = pending.pop()
            for user in self.vars.get(var_id, {}).get("usedBy") or []:
                if user not in direct and user not in downstream:
                    downstream.add(user)
                    pending.append(user)
        outputs = sorted({output for var_id in direct | downstream for output in self.vars.get(var_id, {}).get("outputs") or []})
        for var_id in direct:
            self.vars[var_id]["core"].append(finding["key"])
        for output_id in outputs:
            if output_id in self.outputs:
                self.outputs[output_id]["core"].append(finding["key"])
        return {"sdtm": touched, "adam": sorted(direct), "downstream": sorted(downstream), "outputs": outputs}

    # ---------------------------------------------------------------- assemble

    def datasets(self) -> list[dict]:
        order = list(self.spec_datasets) + sorted({var["ds"] for var in self.vars.values()} - set(self.spec_datasets))
        population = read_json(self.root / "lineage" / "population-counts.json", {}) or {}
        result = []
        for name in order:
            spec = self.spec_datasets.get(name) or {}
            profile = self.profiles.get(name) or {}
            variables = [var["name"] for var in self.vars.values() if var["ds"] == name]
            in_data = list((profile.get("columns") or {}).keys())
            ordered = in_data + [variable for variable in variables if variable not in in_data]
            programs = sorted({var.get("program") for var in self.vars.values() if var["ds"] == name and var.get("program")})
            result.append({"name": name, "class": spec.get("class"), "records": profile.get("records")
                           if profile.get("records") is not None else ((population.get("datasets") or {}).get(name) or {}).get("records"),
                           "armVariable": profile.get("armVariable"), "keys": profile.get("keys") or [], "programs": programs,
                           "sdtmSources": spec.get("sdtm_source") or [], "vars": ordered})
        return result


def build_model(root: Path, profiles: dict | None = None) -> dict:
    model = Model(root, profiles or {})
    model.load_lineage()
    model.load_outputs()
    protocol = model.load_protocol()
    core = model.load_core()
    package = read_json(root / "package.json", {}) or {}
    accuracy = read_json(root / "tfl" / "accuracy.json", {}) or {}
    for var in model.vars.values():
        var["outputs"] = sorted(set(var["outputs"]))
        var["usedBy"] = sorted(set(var["usedBy"]))
        var["core"] = sorted(set(var["core"]))
    for column in model.sdtm.values():
        column["usedBy"] = sorted(set(column["usedBy"]))
        column["readBy"] = sorted(set(column["readBy"]))
        column["core"] = sorted(set(column["core"]))
    for output in model.outputs.values():
        output["core"] = sorted(set(output["core"]))
    return {
        "study": {**protocol["study"], "history": package.get("history") or []},
        "datasets": model.datasets(),
        "vars": model.vars,
        "sdtm": model.sdtm,
        "domains": {name: {"label": domain["label"], "columns": len(domain["columns"])} for name, domain in model.domains.items()},
        "programs": model.programs,
        "outputs": model.outputs,
        "analyses": model.analyses,
        "objectives": protocol["objectives"],
        "endpoints": protocol["endpoints"],
        "plan": model.plan,
        "core": {"standards": core, "findings": model.findings},
        "checks": {"summary": accuracy.get("summary"), "coverage": accuracy.get("coverage"), "populationCounts": accuracy.get("populationCounts"),
                   "warnings": accuracy.get("warnings") or [], "consistency": accuracy.get("consistency") or [],
                   "populations": (read_json(root / "lineage" / "population-counts.json", {}) or {}).get("populations")},
        "gaps": model.gaps,
    }
