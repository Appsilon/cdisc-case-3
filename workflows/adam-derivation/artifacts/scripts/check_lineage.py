"""Build lineage.json from the programs' @derive tags and gate the derivation on it.

lineage.json is the traceability backbone: every ADaM variable -> the program
lines that make it -> its spec entry -> the SDTM variables it reads -> the
TFLs that use it. CORE's report joins its ADaM findings on it, and the define
is generated from it. So it has to be true, and this step checks that it is:

  * every tag parses, names its own program's dataset and a Define-XML origin;
  * the tagged block really mentions the variable it claims to make;
  * every exported column has exactly one tag, and every tag an exported column;
  * every `src=` exists - an SDTM column or a column of another ADaM dataset;
  * every dataset, variable and PARAMCD the ADaM spec demands was produced.

A failure goes back to the agent (feedback.json) while attempts remain.

Result: { needsFix, retry, attempt, problems, counts, summary }
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adamlib import (  # noqa: E402
    INPUTS_DIR, MAX_ATTEMPTS, ORIGINS, SDTM_COLUMNS_PATH, dataset_programs, gate, read_tags, resolve_sources,
)
from mfpkg import OUTPUT_DIR, STEP_OUTPUTS_DIR, StepFailure, run_main, write_result  # noqa: E402

SOURCE_REQUIRED = ("Derived", "Predecessor")
PROBLEM_CAP = 60


def load_spec() -> dict[str, dict]:
    spec = json.loads((INPUTS_DIR / "adam-spec.json").read_text(encoding="utf-8"))
    return {str(dataset.get("name", "")).upper(): dataset for dataset in spec.get("datasets") or []}


def literal_paramcds(dataset: dict) -> set[str]:
    """PARAMCDs the spec names exactly; placeholders such as <LBTESTCD> or ALT/AST are skipped."""
    codes = set()
    for parameter in dataset.get("parameters") or []:
        code = str(parameter.get("paramcd") or "")
        if re.fullmatch(r"[A-Z][A-Z0-9]{0,7}", code):
            codes.add(code)
    return codes


def mentions(code: str, variable: str) -> bool:
    """The block names the variable, or admiral builds it from a prefix (new_vars_prefix = "TRTS" -> TRTSDT)."""
    if re.search(rf"\b{re.escape(variable)}\b", code) is not None:
        return True
    prefixes = re.findall(r"new_vars_prefix\s*=\s*[\"']([A-Z][A-Z0-9]{0,7})[\"']", code)
    return any(variable.startswith(prefix) for prefix in prefixes)


def check(manifests: dict[str, dict], spec: dict[str, dict], sdtm_columns: dict[str, set[str]]) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    entries: list[dict] = []
    adam_columns = {name: {column["name"] for column in manifest["columns"]} for name, manifest in manifests.items()}
    tags_per_variable: dict[str, list[str]] = defaultdict(list)

    for dataset, program in dataset_programs().items():
        blocks, syntax = read_tags(program)
        problems.extend(syntax)
        for block in blocks:
            where = f"{program.name}:{block['tagLine']}"
            if block["origin"] not in ORIGINS:
                problems.append(f"{where}: origin must be one of {', '.join(ORIGINS)}, got '{block['origin']}'")
            if block["origin"] in SOURCE_REQUIRED and not block["sources"]:
                problems.append(f"{where}: origin={block['origin']} needs src=DOMAIN.VARIABLE")
            for target in block["targets"]:
                target_dataset, _, variable = target.partition(".")
                if target_dataset != dataset or variable == "":
                    problems.append(f"{where}: tag target '{target}' must be {dataset}.<VARIABLE> in {program.name}")
                    continue
                if mentions(block["code"], variable) is False:
                    problems.append(f"{where}: {target} is tagged on lines {block['lines'][0]}-{block['lines'][1]}, which never mention {variable}")
                sources = resolve_sources(variable, block["sources"])
                for source in sources:
                    domain, _, source_variable = source.partition(".")
                    known = sdtm_columns.get(domain, set()) | adam_columns.get(domain, set())
                    if source_variable not in known:
                        problems.append(f"{where}: src {source} does not exist in the staged SDTM or the derived ADaM")
                in_spec = variable in {str(item.get("name", "")).upper() for item in (spec.get(dataset) or {}).get("variables") or []}
                tags_per_variable[target].append(where)
                entries.append({
                    "dataset": dataset,
                    "variable": variable,
                    "origin": block["origin"],
                    "program": program.name,
                    "lines": block["lines"],
                    "spec": block["spec"] or (target if in_spec else ""),
                    "sources": sources,
                    "method": block["method"],
                })

    for target, places in tags_per_variable.items():
        if len(places) > 1:
            problems.append(f"{target} is tagged {len(places)} times ({', '.join(places)}): keep exactly one tag per variable")
    for dataset, columns in adam_columns.items():
        untagged = sorted(column for column in columns if f"{dataset}.{column}" not in tags_per_variable)
        if untagged:
            problems.append(f"{dataset.lower()}.R: no @derive tag for column(s) {', '.join(untagged)}")
        phantom = sorted(target for target in tags_per_variable if target.startswith(f"{dataset}.") and target.split(".", 1)[1] not in columns)
        if phantom:
            problems.append(f"{dataset.lower()}.R: tagged but not in the exported dataset: {', '.join(phantom)}")

    for dataset, demand in spec.items():
        if dataset not in manifests:
            problems.append(f"The spec demands {dataset} (used by {', '.join(demand.get('used_by_tables') or []) or 'no table'}), but no {dataset.lower()}.R produced it")
            continue
        missing = sorted(str(item.get("name", "")).upper() for item in demand.get("variables") or []
                         if str(item.get("name", "")).upper() not in adam_columns[dataset])
        if missing:
            problems.append(f"{dataset}: the spec demands variable(s) {', '.join(missing)}, which are not in the dataset")
        missing_codes = sorted(literal_paramcds(demand) - set(manifests[dataset].get("paramcd") or []))
        if missing_codes:
            problems.append(f"{dataset}: the spec demands PARAMCD {', '.join(missing_codes)}, which the dataset does not contain")
    return entries, problems


def consumers(spec: dict[str, dict]) -> dict[str, list[str]]:
    used_by: dict[str, list[str]] = {}
    for dataset, demand in spec.items():
        tables = sorted(str(table) for table in demand.get("used_by_tables") or [])
        for item in demand.get("variables") or []:
            if tables:
                used_by[f"{dataset}.{str(item.get('name', '')).upper()}"] = tables
    return used_by


def main() -> None:
    manifest_path = STEP_OUTPUTS_DIR / "execute-programs" / "manifest.json"
    if manifest_path.is_file() is False:
        raise StepFailure(f"execute-programs left no manifest at {manifest_path}")
    manifests = {item["dataset"]: item for item in json.loads(manifest_path.read_text(encoding="utf-8")).get("datasets") or []}
    sdtm_columns = {domain: set(columns) for domain, columns in json.loads(SDTM_COLUMNS_PATH.read_text(encoding="utf-8")).items()}
    spec = load_spec()

    entries, problems = check(manifests, spec, sdtm_columns)
    lineage = {"variables": entries, "consumers": consumers(spec)}
    (OUTPUT_DIR / "lineage.json").write_text(json.dumps(lineage, indent=2), encoding="utf-8")

    if len(problems) > PROBLEM_CAP:
        problems = problems[:PROBLEM_CAP] + [f"... and {len(problems) - PROBLEM_CAP} more of the same kinds"]
    routing = gate("check-lineage", problems)
    origins = defaultdict(int)
    for entry in entries:
        origins[entry["origin"]] += 1
    counts = {"variables": len(entries), "datasets": len(manifests), "origins": dict(origins)}
    if problems:
        summary = (f"Attempt {routing['attempt']}/{MAX_ATTEMPTS}: lineage gate failed with {len(problems)} problem(s). "
                   + ("Back to the agent." if routing["retry"] else "No attempts left."))
    else:
        summary = (f"Lineage complete: {len(entries)} variable(s) across {len(manifests)} dataset(s) traced to program lines and sources ("
                   + ", ".join(f"{count} {origin}" for origin, count in sorted(origins.items())) + "); every spec demand met.")
    write_result({**routing, "counts": counts, "summary": summary})


if __name__ == "__main__":
    run_main(main)
