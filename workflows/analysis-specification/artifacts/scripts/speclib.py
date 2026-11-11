"""Paths and the deterministic spec gate shared by the analysis-specification steps.

Every step of a run mounts the same worktree at /workspace:

    /workspace/analysis-specification/
        inputs/tlf-plan.json             the approved plan (required)
        inputs/study-model.json          the normalized study (required)
        inputs/sdtm-inventory.json       what the delivered SDTM holds
        inputs/{sap,usdm}/               optional context
        specs/analysis-spec.json         written by the spec agent
        specs/adam-spec.json             written by the spec agent
        specs/reporting-event.json       written by the spec agent (CDISC ARS ReportingEvent)
        feedback.json                    what the last gate rejected, for the agent
        review-feedback.jsonl            every reviewer request, one JSON line each
        attempts.json                    how many times the gate has run since the last review

The gate checks what a script can check for certain, across the three files:
the ARS ReportingEvent is schema-valid and every internal reference resolves;
every planned TLF has exactly one analysis-spec entry and one ARS analysis and
output, and nothing else does; every dataset and variable an analysis uses is
in the ADaM spec; the ADaM spec is what adam-derivation consumes (dataset and
variable names SAS V5 can hold, classes, PARAMCDs, the mandatory derivation
rules and the N-gate) and reads only SDTM that was delivered.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

WORKSPACE_DIR = Path(os.environ.get("MEDIFORCE_WORKSPACE_DIR", "/workspace"))
WORK_DIR = WORKSPACE_DIR / "analysis-specification"
INPUTS_DIR = WORK_DIR / "inputs"
SPECS_DIR = WORK_DIR / "specs"
FEEDBACK_PATH = WORK_DIR / "feedback.json"
REVIEW_FEEDBACK_PATH = WORK_DIR / "review-feedback.jsonl"
ATTEMPTS_PATH = WORK_DIR / "attempts.json"
SCHEMA_PATH = Path(os.environ.get("ARS_SCHEMA_PATH", str(Path(__file__).resolve().parent.parent / "schemas" / "ars_ldm.schema.json")))
MAX_ATTEMPTS = 3

ANALYSIS_SPEC = "analysis-spec.json"
ADAM_SPEC = "adam-spec.json"
REPORTING_EVENT = "reporting-event.json"
SPEC_FILES = (ANALYSIS_SPEC, ADAM_SPEC, REPORTING_EVENT)

CLASSES = ("ADSL", "BDS", "OCCDS", "TTE")
DATASET_NAME = re.compile(r"^AD[A-Z0-9]{1,6}$")
VARIABLE_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,7}$")
PARAMCD = re.compile(r"^[A-Z][A-Z0-9]{0,7}$")
IDENTIFIER = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
SDTM_DOMAIN = re.compile(r"^(SUPP)?[A-Z]{2}[A-Z0-9]{0,4}$")
LIST_ITEM_KEYS = ("analysisId", "outputId")


def load_json(path: Path, problems: list[str]):
    if path.is_file() is False:
        problems.append(f"{path.name} is missing from {path.parent}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        problems.append(f"{path.name} is not valid JSON: {error}")
        return None


def table_id_of(final_id: str) -> str:
    return re.sub(r"^[TLF]-", "", final_id)


def planned_tables(plan: list) -> dict[str, dict]:
    """table_id -> candidate, for every planned and numbered output of the plan."""
    return {table_id_of(str(item["final_id"])): item for item in plan
            if isinstance(item, dict) and item.get("status") == "planned" and item.get("final_id")}


def ars_schema_problems(event: dict) -> list[str]:
    try:
        from jsonschema import Draft7Validator
    except ImportError as error:
        raise RuntimeError("jsonschema is not installed in this image") from error
    validator = Draft7Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    grouped: dict[tuple[str, str], list[str]] = {}
    for error in sorted(validator.iter_errors(event), key=lambda item: [str(part) for part in item.absolute_path]):
        parts = [str(part) for part in error.absolute_path]
        pattern = "/".join("*" if part.isdigit() else part for part in parts) or "(root)"
        grouped.setdefault((pattern, error.message[:300]), []).append("/".join(parts))
    problems = []
    for (pattern, message), locations in grouped.items():
        where = locations[0] if len(locations) == 1 else f"{pattern} ({len(locations)} items, e.g. {locations[0]})"
        problems.append(f"{REPORTING_EVENT} {where}: {message}")
    return problems


def ars_reference_problems(event: dict) -> list[str]:
    """References the JSON Schema cannot express: every id an analysis or the contents list names must exist."""
    def ids(collection: str) -> set[str]:
        return {str(item.get("id")) for item in event.get(collection) or [] if isinstance(item, dict) and item.get("id")}

    targets = {"methodId": ids("methods"), "analysisSetId": ids("analysisSets"), "dataSubsetId": ids("dataSubsets")}
    groupings = ids("analysisGroupings")
    problems = []
    for analysis in event.get("analyses") or []:
        if isinstance(analysis, dict) is False:
            continue
        label = analysis.get("id", "(no id)")
        for key, known in targets.items():
            value = analysis.get(key)
            if value and value not in known:
                problems.append(f"{REPORTING_EVENT} analyses/{label}: {key} '{value}' is not defined")
        for grouping in analysis.get("orderedGroupings") or []:
            if isinstance(grouping, dict) and grouping.get("groupingId") and grouping["groupingId"] not in groupings:
                problems.append(f"{REPORTING_EVENT} analyses/{label}: groupingId '{grouping['groupingId']}' is not defined")

    known = {"analysisId": ids("analyses"), "outputId": ids("outputs")}

    def walk(container, trail: str) -> None:
        if isinstance(container, dict) is False:
            return
        for position, item in enumerate(container.get("listItems") or []):
            if isinstance(item, dict) is False:
                continue
            for key in LIST_ITEM_KEYS:
                if item.get(key) and item[key] not in known[key]:
                    problems.append(f"{REPORTING_EVENT} {trail}/listItems/{position}: {key} '{item[key]}' is not defined")
            walk(item.get("sublist"), f"{trail}/listItems/{position}/sublist")

    walk((event.get("mainListOfContents") or {}).get("contentsList"), "mainListOfContents/contentsList")
    return problems


def adam_spec_problems(spec: dict, tables: set[str], delivered_domains: set[str]) -> list[str]:
    problems = []
    datasets = spec.get("datasets")
    if isinstance(datasets, list) is False or not datasets:
        return [f"{ADAM_SPEC} needs datasets[] (references/adam-spec-schema.md)"]
    names = Counter(str(item.get("name", "")) for item in datasets if isinstance(item, dict))
    problems += [f"{ADAM_SPEC}: dataset {name} is specified {count} times" for name, count in names.items() if count > 1]
    if "ADSL" not in names:
        problems.append(f"{ADAM_SPEC}: ADSL is missing; every other dataset takes its population flags and treatment from it")
    consumed: set[str] = set()
    for dataset in datasets:
        if isinstance(dataset, dict) is False:
            problems.append(f"{ADAM_SPEC}: every datasets[] item must be an object")
            continue
        name = str(dataset.get("name", ""))
        if DATASET_NAME.match(name) is None:
            problems.append(f"{ADAM_SPEC}: dataset name {name!r} is not an ADaM name (AD + up to 6 letters/digits, upper case)")
        if dataset.get("class") not in CLASSES:
            problems.append(f"{ADAM_SPEC} {name}: class must be one of {', '.join(CLASSES)}, got {dataset.get('class')!r}")
        variables = [str(item.get("name", "")) for item in dataset.get("variables") or [] if isinstance(item, dict)]
        if not variables:
            problems.append(f"{ADAM_SPEC} {name}: variables[] is empty")
        bad = [variable for variable in variables if VARIABLE_NAME.match(variable) is None]
        if bad:
            problems.append(f"{ADAM_SPEC} {name}: variable names SAS V5 cannot hold (upper case, 8 characters): {', '.join(bad[:10])}")
        repeated = sorted(variable for variable, count in Counter(variables).items() if count > 1)
        if repeated:
            problems.append(f"{ADAM_SPEC} {name}: variables listed more than once: {', '.join(repeated)}")
        for parameter in dataset.get("parameters") or []:
            code = str((parameter or {}).get("paramcd") or "")
            if code and PARAMCD.match(code) is None and "<" not in code:
                problems.append(f"{ADAM_SPEC} {name}: PARAMCD {code!r} is not 1-8 upper-case letters/digits")
        used_by = {str(table) for table in dataset.get("used_by_tables") or []}
        unknown = sorted(used_by - tables)
        if unknown:
            problems.append(f"{ADAM_SPEC} {name}: used_by_tables names outputs that are not planned: {', '.join(unknown[:10])}")
        consumed |= used_by
        if delivered_domains:
            sources = [str(source).upper() for source in dataset.get("sdtm_source") or []]
            absent = sorted(source for source in sources if SDTM_DOMAIN.match(source) and source not in delivered_domains)
            if absent:
                problems.append(f"{ADAM_SPEC} {name}: sdtm_source {', '.join(absent)} was not delivered "
                                f"(delivered: {', '.join(sorted(delivered_domains))}); block the outputs that need it in the plan instead")
    missing = sorted(tables - consumed)
    if missing:
        problems.append(f"{ADAM_SPEC}: no dataset lists planned output(s) {', '.join(missing[:10])} in used_by_tables")
    if not spec.get("mandatory_derivation_rules"):
        problems.append(f"{ADAM_SPEC}: mandatory_derivation_rules is missing (references/adam-spec-schema.md)")
    if not spec.get("data_quality_gate"):
        problems.append(f"{ADAM_SPEC}: data_quality_gate (the N-gate) is missing (references/adam-spec-schema.md)")
    return problems


def analysis_problems(entries: list, tables: dict[str, dict], spec: dict) -> list[str]:
    problems = []
    variables_of = {str(item.get("name", "")): {str(variable.get("name", "")) for variable in item.get("variables") or [] if isinstance(variable, dict)}
                    for item in spec.get("datasets") or [] if isinstance(item, dict)}
    adsl = variables_of.get("ADSL", set())
    seen = Counter(str(entry.get("table_id", "")) for entry in entries if isinstance(entry, dict))
    problems += [f"{ANALYSIS_SPEC}: table_id {key} has {count} entries" for key, count in seen.items() if count > 1]
    missing = sorted(set(tables) - set(seen))
    if missing:
        problems.append(f"{ANALYSIS_SPEC}: no entry for planned output(s) {', '.join(missing[:15])}")
    extra = sorted(set(seen) - set(tables))
    if extra:
        problems.append(f"{ANALYSIS_SPEC}: entries for outputs that are not planned (blocked, flagged or unknown): {', '.join(extra[:15])}")
    for entry in entries:
        if isinstance(entry, dict) is False:
            problems.append(f"{ANALYSIS_SPEC}: every item must be an object")
            continue
        label = str(entry.get("table_id", "(no table_id)"))
        if not entry.get("methods"):
            problems.append(f"{ANALYSIS_SPEC} {label}: methods[] is empty")
        if not (entry.get("analysisSet") or {}).get("condition"):
            problems.append(f"{ANALYSIS_SPEC} {label}: analysisSet.condition is missing")
        dataset = str((entry.get("dataSubset") or {}).get("dataset", ""))
        if dataset not in variables_of:
            problems.append(f"{ANALYSIS_SPEC} {label}: dataSubset.dataset {dataset!r} is not in {ADAM_SPEC}")
            continue
        available = variables_of[dataset] | adsl
        named = []
        for role in (entry.get("analysisVariables") or {}).values():
            named += IDENTIFIER.findall(str((role or {}).get("variable", "")) if isinstance(role, dict) else str(role))
        grouping = (entry.get("groupingFactor") or {}).get("variable")
        if grouping:
            named.append(str(grouping))
        unknown = sorted({variable for variable in named if variable not in available})
        if unknown:
            problems.append(f"{ANALYSIS_SPEC} {label}: uses {', '.join(unknown)}, not in {ADAM_SPEC} {dataset} or ADSL variables")
    return problems


def coverage_problems(event: dict, tables: dict[str, dict]) -> list[str]:
    """Each planned output is one ARS analysis and one ARS output, keyed by its id."""
    analyses = {str(item.get("id")) for item in event.get("analyses") or [] if isinstance(item, dict)}
    outputs = {str(item.get("id")) for item in event.get("outputs") or [] if isinstance(item, dict)}
    problems = []
    for table_id, candidate in tables.items():
        final_id = str(candidate["final_id"])
        if not {f"AN.{final_id}", f"AN.{table_id}"} & analyses:
            problems.append(f"{REPORTING_EVENT}: planned output {final_id} has no analysis AN.{final_id}")
        if not {f"OUT.{final_id}", f"OUT.{table_id}"} & outputs:
            problems.append(f"{REPORTING_EVENT}: planned output {final_id} has no output OUT.{final_id}")
    return problems


def check_specs(specs_dir: Path = SPECS_DIR, inputs_dir: Path = INPUTS_DIR) -> dict:
    """Run the gate. Result: {problems, counts}."""
    problems: list[str] = []
    plan = load_json(inputs_dir / "tlf-plan.json", problems)
    inventory = load_json(inputs_dir / "sdtm-inventory.json", []) or {}
    entries = load_json(specs_dir / ANALYSIS_SPEC, problems)
    spec = load_json(specs_dir / ADAM_SPEC, problems)
    event = load_json(specs_dir / REPORTING_EVENT, problems)
    if plan is None or entries is None or spec is None or event is None:
        return {"problems": problems, "counts": {}}
    if isinstance(entries, list) is False:
        return {"problems": [f"{ANALYSIS_SPEC} must be an array, one entry per planned output"], "counts": {}}
    if isinstance(spec, dict) is False or isinstance(event, dict) is False:
        return {"problems": [f"{ADAM_SPEC} and {REPORTING_EVENT} must be objects"], "counts": {}}

    tables = planned_tables(plan)
    delivered = {str(domain).upper() for domain in (inventory.get("domains") or {})}
    problems += ars_schema_problems(event)
    problems += ars_reference_problems(event)
    problems += coverage_problems(event, tables)
    problems += adam_spec_problems(spec, set(tables), delivered)
    problems += analysis_problems(entries, tables, spec)

    methods = Counter(str(method.get("type") or method.get("id") or "?") for entry in entries if isinstance(entry, dict)
                      for method in entry.get("methods") or [] if isinstance(method, dict))
    counts = {
        "analyses": len(entries),
        "plannedOutputs": len(tables),
        "datasets": sorted(str(item.get("name")) for item in spec.get("datasets") or [] if isinstance(item, dict)),
        "variables": sum(len(item.get("variables") or []) for item in spec.get("datasets") or [] if isinstance(item, dict)),
        "arsAnalyses": len(event.get("analyses") or []),
        "methods": dict(methods.most_common(12)),
    }
    return {"problems": problems, "counts": counts}


def attempts() -> int:
    if ATTEMPTS_PATH.is_file() is False:
        return 0
    return int(json.loads(ATTEMPTS_PATH.read_text(encoding="utf-8")).get("attempts", 0))


def count_attempt() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    attempt = attempts() + 1
    ATTEMPTS_PATH.write_text(json.dumps({"attempts": attempt}), encoding="utf-8")
    return attempt


def reset_attempts() -> None:
    ATTEMPTS_PATH.unlink(missing_ok=True)
    FEEDBACK_PATH.unlink(missing_ok=True)
